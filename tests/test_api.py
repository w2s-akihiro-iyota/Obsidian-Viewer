"""API の契約テスト（TestClient。httpx は requirements-dev.txt）

- 記事ページのキャッシュは、埋め込んだノートの更新・削除で作り直す（F-4）
- 保留した削除の API は管理者だけ。同期中は 409（B-2 / B-4）
- 新規ノートの保存は、Vault に書けなければビューア側にも書かない（B-2 の削除で消えないように）
- 公開チェック（F-5）: 管理者は「外部の人の表示」（?as=public）で外部向けと同じ本文と、チェック結果を見られる
- 記事ページのヘッダー（D-1）: パンくず・タイトル・メタ情報
"""
import copy
import os
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import cache
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
