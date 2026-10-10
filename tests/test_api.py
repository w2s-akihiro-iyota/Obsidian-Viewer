"""API の契約テスト（TestClient。httpx は requirements-dev.txt）

- 記事ページのキャッシュは、埋め込んだノートの更新・削除で作り直す（F-4）
- 保留した削除の API は管理者だけ。同期中は 409（B-2 / B-4）
- 新規ノートの保存は、Vault に書けなければビューア側にも書かない（B-2 の削除で消えないように）
- 公開チェック（F-5）: 管理者は「外部の人の表示」（?as=public）で外部向けと同じ本文と、チェック結果を見られる
- 記事ページのヘッダー（D-1）: パンくず・タイトル・メタ情報
- ヘルプ（D-5 / X-4）: 6タブ。「書き方」「管理者向け」タブとエディタのショートカットは管理者だけ（外部表示中の管理者にも出す）
- 画面上のショートカット表示（F-9）: ヘルプの表・? のチートシート・下の段のヒントは app/shortcuts.py の定義から描く
- ノート一覧（D-2 / D-10）: 並び替え・タグの件数（外部には公開ノートだけで数える）・条件のチップ・抜粋・非公開の印
- ダッシュボード（F-6 / D-8）: 手入れが必要なノート（リンク切れ・孤立・タグなし）・ヒートマップ・0 件の表示
- ローカルグラフ（F-8）: /api/graph?center=&depth= の点と距離・深さの不正値・404・外部には公開ノートだけ・上限
"""
import copy
import os
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import cache, shortcuts
from app.api import content as content_api
from app.api import editor as editor_api
from app.core import indexing
from app.main import app
from app.models.sync import SyncConfig
from app.services import sync, wikilinks
from app.services.content import render_markdown
from app.services.publish_check import check_publish

ADMIN = "http://localhost:8001"     # 管理用ポート（is_admin_request が管理者とみなす）
PUBLIC = "http://localhost:8000"


@pytest.fixture
def site(tmp_path, monkeypatch):
    for name in ("GLOBAL_FILE_CACHE", "GLOBAL_FILE_TREE_CACHE", "GLOBAL_FILE_TREE_CACHE_PUBLIC", "IMAGE_PATH_CACHE",
                 "MARKDOWN_CACHE", "FILE_NAME_CACHE", "BACKLINK_CACHE", "FORWARD_LINK_CACHE", "SEARCH_INDEX",
                 "SLUG_TO_PATH", "PATH_TO_SLUG"):
        monkeypatch.setattr(cache, name, getattr(cache, name))
    for module in (content_api, editor_api, indexing, wikilinks):
        monkeypatch.setattr(module, "CONTENT_DIR", tmp_path)
    (tmp_path / "親.md").write_text("---\npublish: true\n---\n本文 ![[子]]\n", encoding="utf-8")
    (tmp_path / "子.md").write_text("---\npublish: true\n---\n子の本文v1\n", encoding="utf-8")
    indexing.refresh_global_caches()
    return tmp_path


def _view(client, path="親.md"):
    return client.get(f"/view/{cache.PATH_TO_SLUG[path]}").text


def test_埋め込んだノートを更新すると記事ページも作り直す(site):
    client = TestClient(app, base_url=ADMIN)
    assert "子の本文v1" in _view(client)
    child = site / "子.md"
    child.write_text("---\npublish: true\n---\n子の本文v2\n", encoding="utf-8")
    later = time.time() + 5
    os.utime(child, (later, later))
    assert "子の本文v2" in _view(client)


def test_埋め込んだノートを消すと記事ページも作り直す(site):
    client = TestClient(app, base_url=ADMIN)
    assert "子の本文v1" in _view(client)
    (site / "子.md").unlink()
    assert "子の本文v1" not in _view(client)


def test_保留した削除のAPIは外部から使えない(site):
    client = TestClient(app, base_url=PUBLIC)
    assert client.get("/api/sync/pending-deletions").status_code == 403
    assert client.post("/api/sync/confirm-deletions").status_code == 403


def test_同期中は409を返す(site):
    client = TestClient(app, base_url=ADMIN)
    assert sync._sync_lock.acquire(blocking=False)
    try:
        assert client.post("/api/sync/confirm-deletions").status_code == 409
        assert client.post("/api/sync").status_code == 409
    finally:
        sync._sync_lock.release()


def test_保留した削除の一覧を返す(site):
    client = TestClient(app, base_url=ADMIN)
    res = client.get("/api/sync/pending-deletions")
    assert res.status_code == 200 and res.json() == {"pending": []}


def test_Vaultに書けなければ新規ノートを保存しない(site, monkeypatch, tmp_path_factory):
    not_a_dir = tmp_path_factory.mktemp("vault") / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")   # ディレクトリではないので、この下には書けない
    monkeypatch.setattr(editor_api, "load_config", lambda: SyncConfig(content_src=str(not_a_dir)))
    client = TestClient(app, base_url=ADMIN)
    res = client.post("/api/editor/save", json={"filename": "新しいノート", "content": "本文"})
    assert res.status_code == 500
    assert not (site / "新しいノート.md").exists()


# ---------- F-5: 公開チェック ----------

_CHECK_PAGE = (
    "---\npublish: true\ntags: [資料]\n---\n"
    "[[秘密]] と [[秘密]] と ![[秘密埋め込み]] と [[無いノート]] と ![[無い画像.png]] と [[公開先]] と [[a.png]]\n"
    "```\n[[コード内秘密]]\n```\n`[[コード内秘密]]`\n"
    "```dataview\nLIST FROM \"資料\"\n```\n"
)


@pytest.fixture
def check_site(site):
    """公開ノートから、非公開ノート・存在しないノート・画像・Dataview を参照する Vault"""
    notes = {
        "公開ページ.md": _CHECK_PAGE,
        "秘密.md": "---\npublish: false\n---\n秘密の本文\n",
        "秘密埋め込み.md": "---\npublish: false\n---\n埋め込み秘密の本文\n",
        "コード内秘密.md": "---\npublish: false\n---\nコード内\n",
        "公開先.md": "---\npublish: true\n---\n公開先の本文 [[公開ページ]]\n",
        "資料/公開資料.md": "---\npublish: true\n---\n公開資料\n",
        "資料/非公開資料.md": "---\npublish: false\n---\n非公開資料\n",
    }
    for rel, text in notes.items():
        path = site / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    return site


def _body_of(path):
    return indexing.parse_frontmatter((indexing.CONTENT_DIR / path).read_text(encoding="utf-8"))[1]


def _article(html):
    """記事本文（<article class="markdown-body">）だけを取り出す"""
    m = re.search(r'<article class="markdown-body">(.*?)</article>', html, re.DOTALL)
    assert m, "記事本文が見つからない"
    return m.group(1)


def _get(client, path, **params):
    return client.get(f"/view/{cache.PATH_TO_SLUG[path]}", params=params)


def test_公開チェックは非公開ノートへのリンクを重複なく挙げる(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert [(n.title, n.path) for n in result.private_links] == [("秘密", "秘密.md")]
    assert result.private_links[0].slug == cache.PATH_TO_SLUG["秘密.md"]


def test_公開チェックは非公開ノートの埋め込みを挙げる(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert [n.path for n in result.private_embeds] == ["秘密埋め込み.md"]


def test_公開チェックは存在しないノートへのリンクを挙げる(check_site):
    # [[a.png]]（埋め込みでない画像名）は描画でリンク切れになるので、存在しないリンクとして数える
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert result.missing_links == ("無いノート", "a.png")


def test_公開チェックは見つからない画像を挙げる(check_site, monkeypatch):
    monkeypatch.setattr(wikilinks, "find_image_in_static",
                        lambda name: "/static/images/ある画像.png" if name == "ある画像.png" else None)
    result = check_publish("x.md", "![[無い画像.png]] ![[ある画像.png]] ![[無い画像.png|300]]", True)
    assert result.missing_images == ("無い画像.png",)
    assert result.missing_links == ()


def test_公開チェックはDataviewで外部に出ない結果を挙げる(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert len(result.dataview_gaps) == 1
    gap = result.dataview_gaps[0]
    assert gap.query == 'LIST FROM "資料"'
    assert gap.hidden_count == 1 and [n.title for n in gap.hidden] == ["非公開資料"]


def test_公開チェックはDataviewに差が無ければ挙げない(check_site):
    body = '```dataview\nLIST FROM "資料" WHERE published = true\n```\n```dataview\n壊れたクエリ\n```'
    assert check_publish("x.md", body, True).dataview_gaps == ()


def test_公開チェックはコードの中のリンクとDataviewを数えない(check_site):
    body = "```\n[[秘密]] [[無いノート]]\n```\n`![[秘密埋め込み]]`\n````markdown\n```dataview\nLIST\n```\n````\n"
    assert check_publish("x.md", body, True).issue_count == 0
    page = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert "コード内秘密.md" not in [n.path for n in page.private_links]


def test_公開チェックはノート自身が非公開なことと合計件数を返す(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), False)
    assert result.is_private
    # 非公開ノート自身 1 + 非公開リンク 1 + 非公開埋め込み 1 + 存在しないリンク 2 + 見つからない画像 1 + Dataview 1
    assert result.issue_count == 7
    assert check_publish("公開ページ.md", _body_of("公開ページ.md"), True).issue_count == 6


@pytest.mark.parametrize("src, broken, field", [
    ("[[a.png]]", True, "missing_links"),
    ("![[無い画像.png]]", True, "missing_images"),
    ("![[ある画像.png]]", False, None),
    ("[[#見出し]]", False, None),
    ("[[秘密]]", True, "private_links"),
    ("![[秘密埋め込み]]", True, "private_embeds"),
    ("[[無いノート]]", True, "missing_links"),
    ("[[公開先]]", False, None),
])
def test_描画と公開チェックでリンクの分類が一致する(check_site, monkeypatch, src, broken, field):
    monkeypatch.setattr(wikilinks, "find_image_in_static",
                        lambda name: "/static/images/ある画像.png" if name == "ある画像.png" else None)
    html = render_markdown(src, published_only=True)
    result = check_publish("x.md", src, True)
    assert ("internal-link-broken" in html) == broken
    assert result.issue_count == (1 if field else 0)
    if field:
        assert len(getattr(result, field)) == 1


@pytest.mark.parametrize("src, kind", [
    ("[[a.png]]", "MISSING_NOTE"),
    ("![[無い画像.png]]", "MISSING_IMAGE"),
    ("![[ある画像.png]]", "IMAGE"),
    ("[[#見出し]]", "HEADING"),
    ("[[秘密]]", "PRIVATE_NOTE"),
    ("[[無いノート]]", "MISSING_NOTE"),
    ("[[公開先]]", "NOTE"),
])
def test_リンクの振り分けは1か所で決まる(check_site, monkeypatch, src, kind):
    monkeypatch.setattr(wikilinks, "find_image_in_static",
                        lambda name: "/static/images/ある画像.png" if name == "ある画像.png" else None)
    published = {f["path"] for f in cache.GLOBAL_FILE_CACHE if f.get("published")}
    link = next(wikilinks.iter_wikilinks(src))
    target = wikilinks.classify_link(link, published)
    assert target.kind is wikilinks.LinkKind[kind]
    # 管理者向け（published_paths=None）では非公開ノートもふつうのノートとして扱う
    if kind == "PRIVATE_NOTE":
        assert wikilinks.classify_link(link, None).kind is wikilinks.LinkKind.NOTE


_CACHES_KEPT_BY_CHECK = ("GLOBAL_FILE_CACHE", "BACKLINK_CACHE", "FORWARD_LINK_CACHE", "MARKDOWN_CACHE",
                         "FILE_NAME_CACHE", "PATH_TO_SLUG", "SLUG_TO_PATH")


def test_公開チェックはキャッシュを書き換えない(check_site):
    # 要素の中身（各ノートの dict など）を書き換えても気づけるよう、深いコピーで比べる
    # IMAGE_PATH_CACHE は描画と同じく、見つかった画像の URL を覚えるだけなので対象外
    before = {name: copy.deepcopy(getattr(cache, name)) for name in _CACHES_KEPT_BY_CHECK}
    check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    check_publish("公開ページ.md", _body_of("公開ページ.md"), False)
    assert {name: getattr(cache, name) for name in _CACHES_KEPT_BY_CHECK} == before


def test_管理者の外部表示の本文は外部向けと同じ(check_site):
    admin = _get(TestClient(app, base_url=ADMIN), "公開ページ.md", **{"as": "public"})
    public = _get(TestClient(app, base_url=PUBLIC), "公開ページ.md")
    assert admin.status_code == 200 and public.status_code == 200
    assert _article(admin.text) == _article(public.text)
    assert "internal-link-broken" in _article(admin.text)
    assert f'/view/{cache.PATH_TO_SLUG["秘密.md"]}"' not in _article(admin.text)
    assert "非公開資料" not in _article(admin.text)


def test_管理者の外部表示にはバナーとチェックパネルが出て編集メニューは出ない(check_site):
    html = _get(TestClient(app, base_url=ADMIN), "公開ページ.md", **{"as": "public"}).text
    assert 'class="public-view-banner"' in html and 'class="publish-check-panel"' in html
    assert "/editor?path=" not in html
    # パネルから非公開ノートの管理者用の表示へ飛べる
    assert f'href="/view/{cache.PATH_TO_SLUG["秘密.md"]}"' in html


def test_管理者の通常表示は全件の本文と要確認件数を出しパネルは出さない(check_site):
    client = TestClient(app, base_url=ADMIN)
    _get(client, "公開ページ.md", **{"as": "public"})   # 外部表示のキャッシュが通常表示に混ざらないこと
    html = _get(client, "公開ページ.md").text
    assert f'/view/{cache.PATH_TO_SLUG["秘密.md"]}"' in _article(html)
    assert "非公開資料" in _article(html)
    assert "要確認 6" in html
    assert 'class="publish-check-panel"' not in html and 'class="public-view-banner"' not in html
    assert "/editor?path=" in html


def test_外部ポートではasを付けても何も変わらない(check_site):
    client = TestClient(app, base_url=PUBLIC)
    plain = _get(client, "公開ページ.md").text
    with_as = _get(client, "公開ページ.md", **{"as": "public"}).text
    assert _article(plain) == _article(with_as)
    for html in (plain, with_as):
        assert "publish-check" not in html and "public-view" not in html and "要確認" not in html


def test_管理者の外部表示で非公開ノートを開くと403にせず案内を出す(check_site):
    res = _get(TestClient(app, base_url=ADMIN), "秘密.md", **{"as": "public"})
    assert res.status_code == 200
    assert "このノートは非公開のため、外部からは 403 になります" in res.text


def test_外部では非公開ノートは403のまま(check_site):
    client = TestClient(app, base_url=PUBLIC)
    assert _get(client, "秘密.md").status_code == 403
    assert _get(client, "秘密.md", **{"as": "public"}).status_code == 403


# ---------- D-1: 記事ページのヘッダー ----------

def test_ヘッダーにフォルダのパンくずとタイトルと更新日とリンク元が出る(check_site):
    (check_site / "資料" / "公開資料.md").write_text(
        "---\npublish: true\ntitle: 表示名\n---\n本文\n", encoding="utf-8")
    (check_site / "公開先.md").write_text("---\npublish: true\n---\n[[公開資料]]\n", encoding="utf-8")
    indexing.refresh_global_caches()
    html = _get(TestClient(app, base_url=ADMIN), "資料/公開資料.md").text
    assert 'href="/?q=%E8%B3%87%E6%96%99%2F"' in html          # /?q=資料/ を URL エンコード
    assert re.search(r'<h1 class="view-title">\s*表示名\s*</h1>', html)
    assert re.search(r'<time class="view-updated" datetime="[^"]+\+09:00"', html)
    assert 'href="#backlinks"' in html and 'id="backlinks"' in html


def test_ヘッダーのタイトルはfrontmatterに無ければファイル名(check_site):
    html = _get(TestClient(app, base_url=ADMIN), "秘密.md").text
    assert re.search(r'<h1 class="view-title">\s*秘密\s*</h1>', html)


# ---------- D-1: 本文の先頭の h1 がタイトルと同じなら、本文側を見えなくする ----------

def _view_note(site, rel, text):
    (site / rel).write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    return _article(_get(TestClient(app, base_url=ADMIN), rel).text)


def test_本文先頭のh1がタイトルと同じなら本文側を隠しidは残す(site):
    article = _view_note(site, "同じ見出し.md", "---\npublish: true\n---\n# 同じ**見出し**\n本文\n")
    assert re.search(r'<h1 class="view-title-duplicate" id="[^"]+">', article)


def test_frontmatterのタイトルと同じh1も隠す(site):
    article = _view_note(site, "ファイル名.md", "---\npublish: true\ntitle: 表示名\n---\n# 表示名\n本文\n")
    assert "view-title-duplicate" in article


def test_本文先頭のh1がタイトルと違えば両方出す(site):
    article = _view_note(site, "タイトル.md", "---\npublish: true\n---\n# 別の見出し\n本文\n")
    assert "<h1 id=" in article and "view-title-duplicate" not in article


def test_本文にh1が無ければヘッダーのタイトルだけ(site):
    html = _get(TestClient(app, base_url=ADMIN), "子.md").text
    assert "<h1" not in _article(html)
    assert re.search(r'<h1 class="view-title">\s*子\s*</h1>', html)


def test_先頭でないh1と埋め込みの中のh1は隠さない(site):
    article = _view_note(site, "前置き.md", "---\npublish: true\n---\n前置き\n\n# 前置き\n")
    assert "view-title-duplicate" not in article
    (site / "見出し子.md").write_text("---\npublish: true\n---\n# 埋め込み親\n", encoding="utf-8")
    article = _view_note(site, "埋め込み親.md", "---\npublish: true\n---\n![[見出し子]]\n")
    assert "markdown-embed" in article and "view-title-duplicate" not in article


HELP_TAB_RE = re.compile(r'<button class="help-tab[^"]*" data-tab="([\w-]+)">')
ALL_HELP_TABS = ["about", "basic", "syntax", "keys", "admin", "display"]


def _help_tabs(html):
    return HELP_TAB_RE.findall(html)


def test_管理者のヘルプは6タブで管理者向けとエディタのキーが出る(site):
    html = TestClient(app, base_url=ADMIN).get("/").text
    assert _help_tabs(html) == ALL_HELP_TABS
    assert 'id="help-panel-admin"' in html
    assert "エディタ（管理者のみ）" in html


def test_外部ポートのヘルプは管理者向けタブとエディタのキーを出さない(site):
    client = TestClient(app, base_url=PUBLIC)
    for html in (client.get("/").text, _view(client)):
        # 書き方と管理者向けは、Vault に書く・管理する人だけに出す
        assert _help_tabs(html) == [t for t in ALL_HELP_TABS if t not in ("syntax", "admin")]
        assert 'id="help-panel-syntax"' not in html
        assert 'id="help-panel-admin"' not in html
        assert "エディタ（管理者のみ）" not in html
        assert "<strong>公開チェック</strong>" not in html
        assert "ダッシュボード" not in html
        # 外部の人は閲覧だけなので、編集・同期・公開設定の機能紹介も出さない
        for feature in ("Markdown エディタ", "ファイル同期", "公開設定"):
            assert f"<strong>{feature}</strong>" not in html


def test_管理者の外部表示でもヘルプの管理者向けタブは出る(site):
    html = TestClient(app, base_url=ADMIN).get(f"/view/{cache.PATH_TO_SLUG['親.md']}", params={"as": "public"}).text
    assert 'class="public-view-banner"' in html   # 外部表示になっていること
    assert "/editor?path=" not in html             # ページ側の出し分けは変えない
    assert _help_tabs(html) == ALL_HELP_TABS
    assert 'id="help-panel-admin"' in html and "エディタ（管理者のみ）" in html


# ---------- F-9: 画面上のショートカット表示 ----------

HELP_KEYS_RE = re.compile(r'<table class="help-table help-keys">(.*?)</table>', re.S)
HELP_KEY_ROW_RE = re.compile(r"<tr><td>(.*?)</td><td>(.*?)</td></tr>", re.S)
SHEET_RE = re.compile(r'<div id="shortcut-sheet".*?<!-- /shortcut-sheet -->', re.S)
SHEET_GROUP_RE = re.compile(r'<section class="shortcut-sheet-group" data-group="([\w-]+)"')


def _keys_html(keys, sep=" "):
    """定義のキーを、ヘルプと同じ表記（<kbd>Ctrl</kbd>+<kbd>K</kbd>）にする"""
    return sep.join("+".join(f"<kbd>{key}</kbd>" for key in chord) for chord in keys)


def _help_key_rows(html):
    return [(keys.strip(), desc.strip()) for keys, desc in HELP_KEY_ROW_RE.findall(HELP_KEYS_RE.search(html).group(1))]


def _sheet(html):
    match = SHEET_RE.search(html)
    assert match, "チートシートのモーダルが無い"
    return match.group(0)


def _admin_pages(client):
    slug = cache.PATH_TO_SLUG["親.md"]
    return {path: client.get(path).text for path in ("/", f"/view/{slug}", "/graph", "/dashboard", "/editor")}


def test_ヘルプのショートカット表は定義の行だけを定義の順に出す(site):
    html = TestClient(app, base_url=ADMIN).get("/").text
    expected = [(_keys_html(s.keys), str(s.description_html)) for g in shortcuts.SHORTCUT_GROUPS for s in g.shortcuts]
    assert _help_key_rows(html) == expected
    for group in shortcuts.SHORTCUT_GROUPS:
        assert f'<th colspan="2" scope="colgroup">{group.label}</th>' in html


def test_外部ポートのヘルプ表に管理者だけの行は出ない(site):
    html = TestClient(app, base_url=PUBLIC).get("/").text
    expected = [(_keys_html(s.keys), str(s.description_html))
                for g in shortcuts.visible_groups(False) for s in g.shortcuts]
    assert _help_key_rows(html) == expected
    for shortcut in shortcuts.group("editor").shortcuts:
        assert (_keys_html(shortcut.keys), shortcut.description) not in _help_key_rows(html)


def test_ヘルプにハテナの行と説明文が出る(site):
    for base_url in (ADMIN, PUBLIC):
        html = TestClient(app, base_url=base_url).get("/").text
        assert ("<kbd>?</kbd>", "ショートカット一覧を開く") in _help_key_rows(html)
        assert "どの画面でも <kbd>?</kbd> を押すと、この画面で使えるショートカットを出せます" in html


def test_チートシートは管理者の全ページに出てエディタのグループを含む(site):
    for path, html in _admin_pages(TestClient(app, base_url=ADMIN)).items():
        groups = SHEET_GROUP_RE.findall(_sheet(html))
        assert sorted(groups) == sorted(g.id for g in shortcuts.SHORTCUT_GROUPS), path


def test_チートシートは外部ポートではエディタのグループを含まない(site):
    client = TestClient(app, base_url=PUBLIC)
    for html in (client.get("/").text, _view(client), client.get("/graph").text):
        sheet = _sheet(html)
        assert "editor" not in SHEET_GROUP_RE.findall(sheet)
        assert "エディタ" not in sheet


def test_チートシートはいまの画面を示しその画面のグループを先頭に出す(site):
    pages = _admin_pages(TestClient(app, base_url=ADMIN))
    editor_sheet = _sheet(pages["/editor"])
    assert "いまの画面: エディタ" in editor_sheet
    assert SHEET_GROUP_RE.findall(editor_sheet)[:2] == ["editor", "global"]
    view_sheet = _sheet(pages[f"/view/{cache.PATH_TO_SLUG['親.md']}"])
    assert "いまの画面: 記事ページ" in view_sheet
    assert SHEET_GROUP_RE.findall(view_sheet)[:2] == ["view", "global"]
    assert "いまの画面: ノート一覧" in _sheet(pages["/"])


def test_ファイルツリーの下の段に絞り込み欄とツリーのヒントがある(site):
    html = TestClient(app, base_url=PUBLIC).get("/").text
    assert 'id="file-tree-hints"' in html
    for group_id in ("tree-filter", "tree"):
        for shortcut in shortcuts.group(group_id).shortcuts:
            assert f"{_keys_html(shortcut.keys, '')} {shortcut.short}</span>" in html


def test_エディタ画面の下の段に保存と字下げのキーがある(site):
    html = TestClient(app, base_url=ADMIN).get("/editor").text
    hints = re.search(r'<div class="key-hint-bar editor-key-hints"[^>]*>(.*?)</div>', html, re.S).group(1)
    assert "<kbd>Ctrl</kbd>+<kbd>S</kbd> 保存" in hints
    assert "<kbd>Tab</kbd> 字下げ" in hints


def test_ボタンのツールチップにキーを添える(site):
    editor = TestClient(app, base_url=ADMIN).get("/editor").text
    assert re.search(r'<button id="editor-save-btn"[^>]*title="保存 \(Ctrl\+S\)"[^>]*aria-label="保存 \(Ctrl\+S\)"', editor)
    html = TestClient(app, base_url=PUBLIC).get("/").text
    for button_id in ("help-open-btn", "help-open-btn-mobile"):
        assert re.search(rf'<button id="{button_id}"[^>]*title="ヘルプ・ショートカット一覧 \(\?\)"'
                         rf'[^>]*aria-label="ヘルプ・ショートカット一覧 \(\?\)"', html), button_id


def test_チートシートの各グループに定義の使える場所を出す(site):
    sheet = _sheet(TestClient(app, base_url=ADMIN).get("/").text)
    for group in shortcuts.SHORTCUT_GROUPS:
        contexts = " ".join(sorted(group.contexts))
        assert f'data-group="{group.id}" data-contexts="{contexts}"' in sheet, group.id


def test_フォーカスの場所の目印は定義のidで出す(site):
    html = TestClient(app, base_url=PUBLIC).get("/").text
    assert re.search(rf'id="file-tree-filter"[^>]*data-shortcut-place="{shortcuts.FOCUS_TREE_FILTER}"', html)
    assert re.search(rf'id="file-tree"[^>]*data-shortcut-place="{shortcuts.FOCUS_TREE}"', html)
    assert re.search(rf'class="search-modal-content" data-shortcut-place="{shortcuts.FOCUS_QUICK_SWITCHER}"', html)


def test_クイックスイッチャーの下の段は定義から描く(site):
    html = TestClient(app, base_url=PUBLIC).get("/").text
    footer = re.search(r'<div class="search-modal-footer key-hint-bar">(.*?)</div>', html, re.S).group(1)
    expected = [s for s in shortcuts.group("quick-switcher").shortcuts] + [shortcuts.find_shortcut("global", ("Esc",))]
    assert re.findall(r"<span>(.*?)</span>", footer) == [f"{_keys_html(s.keys, '')} {s.short}" for s in expected]
    assert [s.short for s in expected] == ["選択", "開く", "新しいタブ", "閉じる"]   # 今の文言のまま


# --- ノート一覧（D-2 / D-10）: 並び替え・タグの件数・条件・抜粋・非公開の印 ---

@pytest.fixture
def list_site(site):
    """公開2件・非公開1件。更新日・タイトル・文字数の順がそれぞれ違うように作る"""
    for name in ("親.md", "子.md"):
        (site / name).unlink()
    now = time.time()
    notes = {
        # ファイル名: (本文, 何秒前に更新したか)
        "古い.md": ("---\ntitle: Alpha\npublish: true\ntags: [共通, 公開だけ]\n---\n短い\n", 300),
        "中間.md": ("---\ntitle: Charlie\npublish: true\ntags: [共通]\n---\n" + "中くらいの本文" * 5 + "\n", 100),
        "新しい.md": ("---\ntitle: Bravo\npublish: false\ntags: [共通, 秘密タグ]\n---\n" + "とても長い本文" * 30 + "\n", 0),
    }
    for name, (text, ago) in notes.items():
        path = site / name
        path.write_text(text, encoding="utf-8")
        os.utime(path, (now - ago, now - ago))
    indexing.refresh_global_caches()
    return site


def _titles(html):
    """一覧に出たノートのタイトル（上から順）"""
    return re.findall(r'<div class="file-name">\s*([^<]+?)\s*<', html)


def _tag_row(html):
    m = re.search(r'<div class="tag-row">(.*?)</div>', html, re.S)
    return m.group(1) if m else ""


@pytest.mark.parametrize("sort, expected", [
    ("updated", ["Bravo", "Charlie", "Alpha"]),
    ("updated_asc", ["Alpha", "Charlie", "Bravo"]),
    ("title", ["Alpha", "Bravo", "Charlie"]),
    ("chars", ["Bravo", "Charlie", "Alpha"]),
])
def test_一覧はsortの値で並び替える(list_site, sort, expected):
    html = TestClient(app, base_url=ADMIN).get("/", params={"sort": sort}).text
    assert _titles(html) == expected
    assert re.search(rf'<option value="{sort}" selected>', html)


def test_一覧のsortが不正なら更新日の新しい順(list_site):
    html = TestClient(app, base_url=ADMIN).get("/", params={"sort": "xxx"}).text
    assert _titles(html) == ["Bravo", "Charlie", "Alpha"]
    assert '<option value="updated" selected>' in html


def test_検索中は並び替えを選べず並びはhiddenで引き継ぐ(list_site):
    html = TestClient(app, base_url=ADMIN).get("/", params={"q": "a", "sort": "title"}).text
    assert re.search(r'<select name="sort"[^>]*disabled', html)
    assert '<input type="hidden" name="sort" value="title">' in html


def test_タグの件数は公開状態の絞り込み後の一覧で数える(list_site):
    client = TestClient(app, base_url=ADMIN)
    row_all = _tag_row(client.get("/").text)
    assert '#共通<span class="tag-count">3</span>' in row_all
    assert '#秘密タグ<span class="tag-count">1</span>' in row_all
    row_public = _tag_row(client.get("/", params={"visibility": "public"}).text)
    assert '#共通<span class="tag-count">2</span>' in row_public
    assert "秘密タグ" not in row_public


def test_外部の一覧では非公開ノートのタグが名前も件数も出ない(list_site):
    html = TestClient(app, base_url=PUBLIC).get("/", params={"visibility": "all"}).text
    assert "秘密タグ" not in html
    assert '#共通<span class="tag-count">2</span>' in _tag_row(html)
    assert _titles(html) == ["Charlie", "Alpha"]
    # 公開状態の切り替えも出さない
    assert 'name="visibility"' not in html


def test_選択中のタグは上位に入らなくても上の列に出す(list_site, monkeypatch):
    monkeypatch.setattr(content_api, "LIST_TOP_TAG_COUNT", 1)
    html = TestClient(app, base_url=ADMIN).get("/", params={"tag": "秘密タグ"}).text
    row = _tag_row(html)
    assert "#共通" in row
    assert re.search(r'class="tag-chip active"[^>]*aria-current="true"[^>]*>\s*#秘密タグ', row)
    assert "＋ほか 1" in row     # 公開だけ


def test_絞り込み中は全件数と条件のチップを出し無ければ件数だけ(list_site):
    client = TestClient(app, base_url=ADMIN)
    plain = client.get("/").text
    assert "<b>3 件</b></span>" in plain
    assert "filter-chip" not in plain and "条件を外す" not in plain

    html = client.get("/", params={"visibility": "public", "tag": "共通", "sort": "title"}).text
    assert "<b>2 件</b>（全 3 件中）" in html
    chips = re.findall(r'<a href="([^"]+)"[^>]*class="filter-chip"[^>]*>([^<]+)<', html)
    # × で外すのはその条件だけ。並び替えは残す
    assert ("/?tag=%E5%85%B1%E9%80%9A&amp;sort=title", "公開") in chips
    assert ("/?visibility=public&amp;sort=title", "#共通") in chips
    assert re.search(r'href="/\?sort=title"[^>]*class="filter-clear"', html)


def test_ページ送りは条件と並びを引き継ぐ(list_site, monkeypatch):
    monkeypatch.setattr(content_api, "PER_PAGE", 1)
    html = TestClient(app, base_url=ADMIN).get("/", params={"q": "a", "visibility": "all", "sort": "chars"}).text
    assert re.search(r'href="/\?q=a&amp;sort=chars&amp;page=2"[^>]*hx-get="/\?q=a&amp;sort=chars&amp;page=2"', html)


def test_管理者の一覧は非公開ノートにだけ印を付け外部には出さない(list_site):
    admin = TestClient(app, base_url=ADMIN).get("/").text
    assert admin.count('class="private-mark"') == 1
    assert re.search(r'Bravo\s*<span class="private-mark" title="非公開">', admin)
    assert "file-status-badge" not in admin
    public = TestClient(app, base_url=PUBLIC).get("/").text
    assert "private-mark" not in public
    assert "file-status-badge" not in public


def test_抜粋はMarkdownの記号を除いた本文にする():
    body = (
        "# 見出し\n"
        "- リスト1\n* リスト2\n+ リスト3\n1. 番号\n- [ ] タスク\n"
        "> 引用\n> [!note] 注意の題\n> 中身\n"
        "**太字** と _斜体_ と ~~消し~~ と ==印== と `code` と snake_case\n"
        "```python\nprint(1)\n```\n"
        "[[ノート|別名]] と [[別ノート]] と [リンク](https://example.com)\n"
        "![[画像.png]] ![alt](img.png) <span>タグ</span>\n\n\n  空白   つめる\n"
    )
    assert indexing.make_preview(body) == (
        "見出し リスト1 リスト2 リスト3 番号 タスク 引用 注意の題 中身 "
        "太字 と 斜体 と 消し と 印 と code と snake_case print(1) "
        "別名 と 別ノート と リンク タグ 空白 つめる"
    )


def test_抜粋は200文字で切る():
    assert len(indexing.make_preview("あ" * 300)) == 200
    assert indexing.make_preview("") == ""


def test_外部からvisibility_privateを指定しても公開ノートだけ(list_site):
    html = TestClient(app, base_url=PUBLIC).get("/", params={"visibility": "private"}).text
    assert _titles(html) == ["Charlie", "Alpha"]
    assert "filter-chip" not in html


def test_外部から非公開ノートだけのタグを指定すると0件で中身を出さない(list_site):
    html = TestClient(app, base_url=PUBLIC).get("/", params={"tag": "秘密タグ"}).text
    assert _titles(html) == []
    assert "<b>0 件</b>" in html
    assert "Bravo" not in html and "とても長い本文" not in html
    # 選んだタグは上の列に出るが、件数は 0（公開ノートだけで数える）
    assert '#秘密タグ<span class="tag-count">0</span>' in _tag_row(html)


def test_ページが総ページ数を超えたら最後のページに丸める(list_site, monkeypatch):
    monkeypatch.setattr(content_api, "PER_PAGE", 2)
    client = TestClient(app, base_url=ADMIN)
    html = client.get("/", params={"page": 99}).text
    assert _titles(html) == ["Alpha"]
    assert "2 / 2 ページ" in html
    empty = client.get("/", params={"page": 5, "q": "該当なし"}).text
    assert _titles(empty) == [] and "条件に合うノートはありません" in empty


def test_数値のタイトルでも一覧の検索と並び替えができる(list_site):
    (list_site / "年.md").write_text("---\ntitle: 2024\npublish: true\n---\n本文\n", encoding="utf-8")
    indexing.refresh_global_caches()
    client = TestClient(app, base_url=ADMIN)
    assert _titles(client.get("/", params={"q": "2024"}).text) == ["2024"]
    assert _titles(client.get("/", params={"sort": "title"}).text)[0] == "2024"


def test_抜粋のリンクの閉じ忘れは次の行を巻き込まない():
    assert indexing.make_preview("[閉じ忘れ](http://a\n次の行) と [[壊れ\n本文]]") == "[閉じ忘れ](http://a 次の行) と [[壊れ 本文]]"


def test_ダッシュボードのタグ分布は件数の多い順に上位だけ(list_site, monkeypatch):
    from app.api import dashboard as dashboard_api
    monkeypatch.setattr(dashboard_api, "DASHBOARD_TOP_TAG_COUNT", 1)
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    assert "共通" in html
    assert "秘密タグ" not in html and "公開だけ" not in html



# ---------- F-6 / D-8: ダッシュボード ----------

@pytest.fixture
def health_site(site):
    """リンク切れ 2 件・孤立 2 件・タグなし 1 件になる Vault（親.md / 子.md は消す）"""
    for name in ("親.md", "子.md"):
        (site / name).unlink()
    now = time.time()
    notes = {
        # ファイル名: (本文, 何秒前に更新したか)
        "ハブ.md": ("---\npublish: true\ntags: [索引]\n---\n"
                    "[[葉]] [[無いA]] [[無いB]] [[無いC]] [[無いD]] [[無いA]] [[ハブ]]\n", 300),
        "葉.md": ("---\npublish: false\n---\n[[ハブ]] ![[消えた]]\n", 200),
        "コードだけ.md": ("---\ntags: [メモ]\n---\n```\n[[コード内の無いノート]]\n```\n`[[インラインの無いノート]]`\n", 100),
        "孤立.md": ("---\ntags: [メモ]\n---\n[[#見出し]] [[#]]\n", 0),
    }
    for name, (text, ago) in notes.items():
        path = site / name
        path.write_text(text, encoding="utf-8")
        os.utime(path, (now - ago, now - ago))
    indexing.refresh_global_caches()
    return site


def _health_card(html, id_):
    m = re.search(rf'<button type="button" class="health-card" id="health-card-{id_}"(.*?)</button>', html, re.S)
    assert m, id_
    return m.group(1)


def _health_rows(html, id_):
    """表の行（ノート名, 原因）"""
    m = re.search(rf'id="health-panel-{id_}".*?<tbody>(.*?)</tbody>', html, re.S)
    assert m, id_
    return [(title, cause.strip()) for title, cause in re.findall(
        r'<a href="/view/[^"]+">([^<]+)</a>.*?<td class="health-cause">([^<]*)</td>', m.group(1), re.S)]


def test_ダッシュボードはリンク切れ孤立タグなしを数える(health_site):
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    counts = {id_: re.search(r'class="health-card-value">([^<]+)<', _health_card(html, id_)).group(1)
              for id_ in ("broken", "orphan", "untagged")}
    assert counts == {"broken": "2", "orphan": "2", "untagged": "1"}


def test_リンク切れの表は切れたリンク先を3件までと残りの件数を出す(health_site):
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    # 最終更新の新しい順。自分へのリンク・存在するノート・重複は数えない。埋め込みの ![[ノート]] も数える
    assert _health_rows(html, "broken") == [("葉", "消えた"), ("ハブ", "無いA、無いB、無いC ほか1件")]
    # 孤立: ハブ（葉から）・葉（ハブから）はリンクされている。自分へのリンクは数えない
    assert [t for t, _ in _health_rows(html, "orphan")] == ["孤立", "コードだけ"]
    assert [t for t, _ in _health_rows(html, "untagged")] == ["葉"]


def test_コードの中のリンクはリンク切れに数えない(health_site):
    files = {f["path"]: f for f in cache.GLOBAL_FILE_CACHE}
    assert files["コードだけ.md"]["missing_links"] == []
    assert files["孤立.md"]["missing_links"] == []      # [[#見出し]] と [[#]] も数えない
    # 公開チェックと同じ判定（同じ本文なら同じ名前を挙げる）
    for path in ("ハブ.md", "葉.md", "コードだけ.md"):
        assert tuple(files[path]["missing_links"]) == check_publish(path, _body_of(path), True).missing_links


def test_カードは表を開閉でき非公開ノートには印を付ける(health_site):
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    card = _health_card(html, "broken")
    assert 'aria-expanded="false"' in card and 'aria-controls="health-panel-broken"' in card
    assert re.search(r'id="health-panel-broken"[^>]*hidden', html)
    panel = re.search(r'id="health-panel-untagged".*?</table>', html, re.S).group(0)
    assert re.search(r'>葉</a><span class="private-mark" title="非公開">', panel)


def test_0件のカードは押せずなしと出し表を作らない(site):
    # 親 ⇄ 子 にリンクを張り、タグも付けて 0 件にする
    (site / "親.md").write_text("---\npublish: true\ntags: [a]\n---\n![[子]]\n", encoding="utf-8")
    (site / "子.md").write_text("---\npublish: true\ntags: [a]\n---\n[[親]]\n", encoding="utf-8")
    indexing.refresh_global_caches()
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    for id_ in ("broken", "orphan", "untagged"):
        card = _health_card(html, id_)
        assert "disabled" in card and "aria-controls" not in card
        assert 'class="health-card-value">なし<' in card
        assert f'id="health-panel-{id_}"' not in html


def test_表は上限までで残りはほかN件(site, monkeypatch):
    from app.api import dashboard as dashboard_api
    monkeypatch.setattr(dashboard_api, "DASHBOARD_HEALTH_ROW_LIMIT", 1)
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    # 親・子ともにタグなし。表は 1 件で、残りは「ほか 1 件」
    assert len(_health_rows(html, "untagged")) == 1
    assert "ほか 1 件" in html


def test_ノートが無いときは最近の更新とタグ分布にまだありませんと出す(site):
    for name in ("親.md", "子.md"):
        (site / name).unlink()
    indexing.refresh_global_caches()
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    assert html.count('<p class="dashboard-empty">まだありません</p>') == 2
    assert "dashboard-recent-list" not in html and "dashboard-tag-bars" not in html


def test_最近の更新は非公開ノートにだけ印を付け公開中バッジは出さない(health_site):
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    recent = re.search(r'<ul class="dashboard-recent-list">(.*?)</ul>', html, re.S).group(1)
    # 公開はハブだけ。ほかの 3 件（publish を書いていないノートも）に印を付ける
    assert recent.count('class="private-mark"') == 3
    assert re.search(r'葉</span>\s*<span class="dashboard-recent-meta">\s*<span class="private-mark"', recent)
    assert re.search(r'ハブ</span>\s*<span class="dashboard-recent-meta">\s*\d', recent)
    assert "file-status-badge" not in html and "公開中" not in html


def test_外部ポートからダッシュボードは403(health_site):
    assert TestClient(app, base_url=PUBLIC).get("/dashboard").status_code == 403


def test_ヒートマップは53列で月のラベルは月初の週の列に置く():
    from datetime import datetime
    from app.core.heatmap import build_heatmap
    files = [{"updated": "2026-10-08 10:00", "char_count": 6000}, {"updated": "2026-10-08 11:00", "char_count": 10},
             {"updated": "2026-10-01 09:00", "char_count": 500}]
    cells, labels = build_heatmap(files, datetime(2026, 10, 10, 12, 0))   # 土曜
    assert len(cells) == 53 * 7                       # 今週の土曜で終わるので 53 列ちょうど
    assert cells[0]["date"] == "2025-10-05"           # 日曜始まり
    by_date = {c["date"]: c for c in cells}
    assert by_date["2026-10-08"]["count"] == 6010 and by_date["2026-10-08"]["level"] == 3
    assert by_date["2026-10-01"]["level"] == 1 and by_date["2026-10-02"]["level"] == 0
    # 2025-11-01（土）は 4 列目。最初の月とは 3 列空いているので両方出す
    assert [(label["label"], label["column"]) for label in labels[:2]] == [("10月", 1), ("11月", 4)]
    # 2026-10-01 は 52 列目。右端に近いので列の右端にそろえる
    last = labels[-1]
    assert last["label"] == "10月" and last["column"] == 52 and last["at_end"]
    # 最初の月の列が 2 列しか無ければ、最初の月は出さない（2025-10-12 始まりで、10 月の列は 2 列）
    _, labels = build_heatmap([], datetime(2026, 10, 17, 12, 0))
    assert labels[0]["label"] == "11月"
    assert all(1 <= label["column"] <= 53 and label["column"] + label["span"] - 1 <= 53 for label in labels)


# ---------- F-8: ローカルグラフ ----------

@pytest.fixture
def graph_site(site):
    """中心 → A → A2、中心 → 秘密B → B2、C → 中心。孤立はどこにもつながらない（親・子は別の島）"""
    notes = {
        "中心.md": "---\npublish: true\n---\n[[A]] と [[秘密B]]\n",
        "A.md": "---\npublish: true\n---\n[[A2]]\n",
        "A2.md": "---\npublish: true\n---\n二歩先\n",
        "秘密B.md": "---\npublish: false\n---\n[[B2]]\n",
        "B2.md": "---\npublish: true\n---\n非公開を経由した二歩先\n",
        "C.md": "---\npublish: true\n---\n[[中心]]\n",
        "孤立.md": "---\npublish: true\n---\nリンクなし\n",
    }
    for rel, text in notes.items():
        (site / rel).write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    return site


def _local(client, center, **params):
    return client.get("/api/graph", params={"center": center, **params})


def _distances(res):
    assert res.status_code == 200
    return {n["id"]: n["distance"] for n in res.json()["nodes"]}


def test_ローカルグラフは1歩と2歩の点と距離を返す(graph_site):
    client = TestClient(app, base_url=ADMIN)
    slug = cache.PATH_TO_SLUG["中心.md"]
    assert _distances(_local(client, slug, depth=1)) == {"中心.md": 0, "A.md": 1, "秘密B.md": 1, "C.md": 1}
    res = _local(client, slug, depth=2)
    assert _distances(res) == {"中心.md": 0, "A.md": 1, "秘密B.md": 1, "C.md": 1, "A2.md": 2, "B2.md": 2}
    links = {(l["source"], l["target"]) for l in res.json()["links"]}
    assert links == {("中心.md", "A.md"), ("中心.md", "秘密B.md"), ("A.md", "A2.md"),
                     ("秘密B.md", "B2.md"), ("C.md", "中心.md")}
    assert res.json()["center"] == "中心.md" and res.json()["truncated"] is False


def test_ローカルグラフの中心はパスでも指定できリンクが無ければ中心だけ(graph_site):
    client = TestClient(app, base_url=ADMIN)
    assert _distances(_local(client, "中心.md")) == {"中心.md": 0, "A.md": 1, "秘密B.md": 1, "C.md": 1}
    res = _local(client, cache.PATH_TO_SLUG["孤立.md"], depth=2)
    assert _distances(res) == {"孤立.md": 0} and res.json()["links"] == []


@pytest.mark.parametrize("depth", ["0", "3", "abc", "-1", ""])
def test_ローカルグラフの深さが1と2以外なら1(graph_site, depth):
    client = TestClient(app, base_url=ADMIN)
    assert set(_distances(_local(client, "中心.md", depth=depth)).values()) == {0, 1}


def test_ローカルグラフの中心が無ければ404(graph_site):
    assert _local(TestClient(app, base_url=ADMIN), "無いノート").status_code == 404


def test_外部から非公開の中心を指定すると404(graph_site):
    assert _local(TestClient(app, base_url=PUBLIC), cache.PATH_TO_SLUG["秘密B.md"]).status_code == 404
    assert _local(TestClient(app, base_url=PUBLIC), "秘密B.md").status_code == 404
    # 管理者の外部表示（?as=public）も外部と同じ
    assert _local(TestClient(app, base_url=ADMIN), "秘密B.md", **{"as": "public"}).status_code == 404


def test_外部のローカルグラフは非公開ノートを経由した2歩先を出さない(graph_site):
    expected = {"中心.md": 0, "A.md": 1, "C.md": 1, "A2.md": 2}
    assert _distances(_local(TestClient(app, base_url=PUBLIC), "中心.md", depth=2)) == expected
    assert _distances(_local(TestClient(app, base_url=ADMIN), "中心.md", depth=2, **{"as": "public"})) == expected


def test_外部の全体グラフは公開ノートだけで距離を付けない(graph_site):
    data = TestClient(app, base_url=PUBLIC).get("/api/graph").json()
    ids = {n["id"] for n in data["nodes"]}
    assert "秘密B.md" not in ids and {"中心.md", "B2.md", "孤立.md"} <= ids
    assert all("distance" not in n for n in data["nodes"])
    assert all(l["source"] != "秘密B.md" and l["target"] != "秘密B.md" for l in data["links"])


def test_ローカルグラフは上限で中心に近い点から残す(graph_site, monkeypatch):
    from app.core import graph as graph_core
    monkeypatch.setattr(graph_core, "LOCAL_GRAPH_MAX_NODES", 4)
    res = _local(TestClient(app, base_url=ADMIN), "中心.md", depth=2)
    assert _distances(res) == {"中心.md": 0, "A.md": 1, "秘密B.md": 1, "C.md": 1}
    assert res.json()["truncated"] is True
    assert all(l["source"] in _distances(res) and l["target"] in _distances(res) for l in res.json()["links"])


def test_記事ページにつながりのパネルと全体グラフへのリンクを出す(graph_site):
    slug = cache.PATH_TO_SLUG["中心.md"]
    html = _view(TestClient(app, base_url=ADMIN), "中心.md")
    assert re.search(r'<section class="local-graph" id="local-graph" role="dialog"[^>]*hidden', html)
    assert f'data-center="{slug}"' in html and 'data-public="false"' in html
    # d3 と描画処理は開いたときに読み込むので、ページの script には無く、読み込み先だけを渡す
    assert 'data-d3-src="https://cdn.jsdelivr.net/npm/d3@7/' in html and 'data-render-src="/static/js/modules/graph-render.js' in html
    assert not re.search(r'<script src="[^"]*(d3@7|graph-render\.js)', html)
    assert f'href="/graph?focus={slug}"' in html
    # 深さの切り替えは config の LOCAL_GRAPH_DEPTHS から作り、先頭を選んでおく
    assert re.findall(r'name="local-graph-depth" value="(\d+)"', html) == ["1", "2"]
    assert 'value="1" id="local-graph-depth-1" checked' in html
    html = _get(TestClient(app, base_url=ADMIN), "中心.md", **{"as": "public"}).text
    assert 'data-public="true"' in html


def test_全体グラフのページはd3と描画処理を読み込む(graph_site):
    html = TestClient(app, base_url=PUBLIC).get("/graph").text
    assert re.search(r'<script src="https://cdn.jsdelivr.net/npm/d3@7/[^"]*" defer>', html)
    assert re.search(r'<script src="/static/js/modules/graph-render\.js[^"]*" defer>', html)


TOGGLE_RE = re.compile(r'<button type="button" class="local-graph-toggle[^"]*" id="local-graph-toggle".*?</button>', re.S)
COUNT_RE = re.compile(r'<span class="local-graph-count" aria-hidden="true">(\d+)</span>')


def _toggle(html):
    match = TOGGLE_RE.search(html)
    assert match, "つながりのボタンが無い"
    return match.group(0)


def test_つながりのボタンはショートカットの定義から名前とキーを出す(graph_site):
    button = _toggle(_view(TestClient(app, base_url=ADMIN), "中心.md"))
    for attr in ("title", "aria-label"):
        assert f'{attr}="つながり (G)"' in button
    assert 'aria-expanded="false"' in button and 'aria-controls="local-graph"' in button
    # 開閉のキーは JS に持たせず、定義から渡す
    assert f'data-shortcut-key="{shortcuts.find_shortcut("view", ("G",)).keys[0][0]}"' in button


def test_つながりのボタンの数は1歩でつながるノートの数(graph_site):
    client = TestClient(app, base_url=ADMIN)
    expected = len(_distances(_local(client, "中心.md", depth=1))) - 1
    button = _toggle(_view(client, "中心.md"))
    assert COUNT_RE.findall(button) == [str(expected)] and expected == 3   # A・秘密B・C（リンク元の C も数える）
    assert "is-empty" not in button


def test_つながりが無いノートはボタンに数を出さず薄くする(graph_site):
    button = _toggle(_view(TestClient(app, base_url=ADMIN), "孤立.md"))
    assert not COUNT_RE.search(button)
    assert 'class="local-graph-toggle is-empty"' in button


def test_外部ではつながりの数を公開ノートだけで数える(graph_site):
    # 中心 → 秘密B（非公開）は数えない。管理者の外部表示も同じ
    assert COUNT_RE.findall(_toggle(_view(TestClient(app, base_url=PUBLIC), "中心.md"))) == ["2"]
    html = _get(TestClient(app, base_url=ADMIN), "中心.md", **{"as": "public"}).text
    assert COUNT_RE.findall(_toggle(html)) == ["2"]
    # 非公開ノートだけにつながる公開ノートは 0 件（数を出さない）
    button = _toggle(_view(TestClient(app, base_url=PUBLIC), "B2.md"))
    assert not COUNT_RE.search(button) and "is-empty" in button
    assert COUNT_RE.findall(_toggle(_view(TestClient(app, base_url=ADMIN), "B2.md"))) == ["1"]


def test_ショートカットの定義に記事ページのGがありヘルプとチートシートに載る(graph_site):
    shortcut = shortcuts.find_shortcut("view", ("G",))
    assert shortcut.description == "つながりを開く・閉じる" and shortcut.short == "つながり"
    assert shortcuts.group("view").contexts == frozenset({"view"})
    for base_url in (ADMIN, PUBLIC):
        html = _view(TestClient(app, base_url=base_url), "中心.md")
        assert ("<kbd>G</kbd>", "つながりを開く・閉じる") in _help_key_rows(html)
        sheet = _sheet(html)
        assert SHEET_GROUP_RE.findall(sheet)[0] == "view"   # 記事ページでは記事ページのグループを先頭に出す
        assert "<tr><td><kbd>G</kbd></td><td>つながり</td></tr>" in sheet
        # ヘルプの「グラフビュー」の説明
        assert "記事ページの<b>右上のボタン</b>（<kbd>G</kbd>）で" in html