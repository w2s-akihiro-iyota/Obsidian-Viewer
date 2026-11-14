"""API の契約テスト（TestClient。httpx2 は requirements-dev.txt）

- 記事ページのキャッシュは、埋め込んだノートの更新・削除で作り直す（F-4）
- 保留した削除の API は管理者だけ。同期中は 409（B-2 / B-4）
- 新規ノートの保存は、Vault に書けなければビューア側にも書かない（B-2 の削除で消えないように）
- 公開チェック（F-5）: 管理者は「外部の人の表示」（?as=public）で外部向けと同じ本文と、チェック結果を見られる
  - 埋め込んだ公開ノートの中も、描画と同じ条件でたどって同じ項目を調べ、書いてあるノートを添える（X-5）
- 外部の人の表示のサイドバー（X-7）: ツリー・検索・プレビューも外部の人と同じ（公開ノートだけ）
- 記事ページのヘッダー（D-1）: パンくず・タイトル・メタ情報
- ヘルプ（D-5 / X-4）: 6タブ。「書き方」「管理者向け」タブとエディタのショートカットは管理者だけ（外部表示中の管理者にも出す）
- 画面上のショートカット表示（F-9）: ヘルプの表・? のチートシート・下の段のヒントは app/shortcuts.py の定義から描く
- ノート一覧（D-2 / D-10）: 並び替え・タグの件数（外部には公開ノートだけで数える）・条件のチップ・抜粋・非公開の印
  - 検索欄の tag:・path: はクイックスイッチャーと同じく絞り込む（B-8）
- ダッシュボード（F-6 / D-8）: 手入れが必要なノート（リンク切れ・孤立・タグなし）・ヒートマップ・0 件の表示
- ローカルグラフ（F-8）: /api/graph?center=&depth= の点と距離・深さの不正値・404・外部には公開ノートだけ・上限
  - グラフは索引の作り直しで作り、記事ページと /api/graph はそれを使う（Q-15）
- ノートを読む回数（Q-1）: 索引の作り直しは各ノートを 1 回だけ読む。記事ページは描画キャッシュが効いていれば読み直さない
- 先読み（F-15）: どの画面も、先読みするのは同じサイトの記事（/view/*）だけ。外部サイト・添付・エディタ・API・新しいタブ・download は対象にしない
"""
import builtins
import copy
import json
import os
import pathlib
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import cache, shortcuts
from app.config import JST
from app.api import content as content_api
from app.api import editor as editor_api
from app.core import indexing
from app.core.frontmatter import parse_frontmatter
from app.main import app
from app.models.sync import SyncConfig
from app.services import sync, wikilinks
from app.services.content import render_markdown
from app.services.images import MediaIndex
from app.services.publish_check import check_publish
from app.utils.messages import get_system

ADMIN = "http://localhost:8001"     # 管理用ポート（is_admin_request が管理者とみなす）
PUBLIC = "http://localhost:8000"


@pytest.fixture
def site(tmp_path, monkeypatch, isolated_caches):
    for module in (content_api, editor_api, indexing, wikilinks):
        monkeypatch.setattr(module, "CONTENT_DIR", tmp_path)
    # 添付の置き場はノートと別のフォルダ（本物の media/ を索引に入れない）
    monkeypatch.setattr(indexing, "MEDIA_DIR", tmp_path.parent / f"{tmp_path.name}-media")
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
    return parse_frontmatter((indexing.CONTENT_DIR / path).read_text(encoding="utf-8"))[1]


def _article(html):
    """記事本文（<article class="markdown-body">）だけを取り出す"""
    m = re.search(r'<article class="markdown-body">(.*?)</article>', html, re.DOTALL)
    assert m, "記事本文が見つからない"
    return m.group(1)


def _get(client, path, **params):
    return client.get(f"/view/{cache.PATH_TO_SLUG[path]}", params=params)


def _names(issues):
    """存在しないノート・見つからない画像の名前（書いてある場所は見ない）"""
    return [i.name for i in issues]


def test_公開チェックは非公開ノートへのリンクを重複なく挙げる(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert [(i.note.title, i.note.path, i.via) for i in result.private_links] == [("秘密", "秘密.md", None)]
    assert result.private_links[0].note.slug == cache.PATH_TO_SLUG["秘密.md"]


def test_公開チェックは非公開ノートの埋め込みを挙げる(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert [i.note.path for i in result.private_embeds] == ["秘密埋め込み.md"]


def test_公開チェックは存在しないノートへのリンクを挙げる(check_site):
    # [[a.png]]（埋め込みでない画像名）は描画でリンク切れになるので、存在しないリンクとして数える
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    assert _names(result.missing_links) == ["無いノート", "a.png"]


def test_公開チェックは見つからない画像を挙げる(check_site, monkeypatch):
    monkeypatch.setattr(cache, "MEDIA_INDEX", MediaIndex(paths=frozenset({"ある画像.png"}),
                                                        by_name={"ある画像.png": "ある画像.png"}))
    result = check_publish("x.md", "![[無い画像.png]] ![[ある画像.png]] ![[無い画像.png|300]]", True)
    assert _names(result.missing_images) == ["無い画像.png"]
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
    assert "コード内秘密.md" not in [i.note.path for i in page.private_links]


def test_公開チェックはノート自身が非公開なことと合計件数を返す(check_site):
    result = check_publish("公開ページ.md", _body_of("公開ページ.md"), False)
    assert result.is_private
    # 非公開ノート自身 1 + 非公開リンク 1 + 非公開埋め込み 1 + 存在しないリンク 2 + 見つからない画像 1 + Dataview 1
    assert result.issue_count == 7
    assert check_publish("公開ページ.md", _body_of("公開ページ.md"), True).issue_count == 6


# ---------- X-5: 埋め込んだ公開ノートの中も調べる ----------

_EMBED_NOTES = {
    # 公開チェックの項目を全部含む、公開の部品
    "部品.md": "---\npublish: true\n---\n部品の本文 [[秘密]] ![[秘密埋め込み]] [[無い部品リンク]] ![[無い部品画像.png]]\n"
               "```dataview\nLIST FROM \"資料\"\n```\n",
    "外枠.md": "---\npublish: true\n---\n外枠の本文\n\n![[部品]]\n",
    "節つき.md": "---\npublish: true\n---\n## 出す節\n[[秘密]]\n## 出さない節\n[[無い節外リンク]]\n",
    "深い1.md": "---\npublish: true\n---\n![[深い2]]\n",
    "深い2.md": "---\npublish: true\n---\n![[深い3]]\n",
    "深い3.md": "---\npublish: true\n---\n深い3の本文 [[秘密]]\n",
    "ループ.md": "---\npublish: true\n---\nループの本文 ![[ループ元]]\n",
    "ループ元.md": "---\npublish: true\n---\n![[ループ]] [[秘密]]\n",
    "秘密の部品.md": "---\npublish: false\n---\n秘密の部品の本文 [[秘密]]\n",
    "部品を埋め込むページ.md": "---\npublish: true\n---\n[[秘密]]\n\n![[部品]]\n",
}


@pytest.fixture
def embed_check_site(check_site):
    """check_site に、公開チェックの項目を含む公開ノートと、それを埋め込むノートを足す"""
    for rel, text in _EMBED_NOTES.items():
        (check_site / rel).write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    return check_site


def _via(issues):
    return [i.via.path if i.via else None for i in issues]


def test_公開チェックは埋め込んだ公開ノートの中もページ本体と同じ項目を調べる(embed_check_site):
    result = check_publish("x.md", "[[秘密]]\n\n![[部品]]\n", True)
    # 同じ非公開ノートでも、書いてある場所が違えば別に挙げる。ページ本体のものが先
    assert [(i.note.path, v) for i, v in zip(result.private_links, _via(result.private_links))] == [
        ("秘密.md", None), ("秘密.md", "部品.md")]
    assert [i.note.path for i in result.private_embeds] == ["秘密埋め込み.md"]
    assert _names(result.missing_links) == ["無い部品リンク"] and _names(result.missing_images) == ["無い部品画像.png"]
    assert len(result.dataview_gaps) == 1 and result.dataview_gaps[0].hidden_count == 1
    for issues in (result.private_embeds, result.missing_links, result.missing_images, result.dataview_gaps):
        assert _via(issues) == ["部品.md"]
    assert result.private_links[1].via.title == "部品"
    assert result.issue_count == 6


def test_入れ子の埋め込みではリンクを書いてあるノートを場所として挙げる(embed_check_site):
    result = check_publish("x.md", "![[外枠]]\n", True)
    assert _via(result.private_links) == ["部品.md"] and _via(result.private_embeds) == ["部品.md"]


def test_見出しの埋め込みはその節の中だけ調べる(embed_check_site):
    result = check_publish("x.md", "![[節つき#出す節]]\n", True)
    assert _via(result.private_links) == ["節つき.md"]
    assert result.missing_links == ()


def test_描画で中身が出ない埋め込みの先は調べない(embed_check_site):
    # 深すぎる入れ子（深い3 は埋め込まずリンクにとどめる）
    assert check_publish("x.md", "![[深い1]]\n", True).issue_count == 0
    assert "深い3の本文" not in render_markdown("![[深い1]]\n", published_only=True)
    # ループ（ループ → ループ元 は埋め込まない）。ページ本体の [[秘密]] だけ
    loop = check_publish("ループ元.md", _body_of("ループ元.md"), True)
    assert _via(loop.private_links) == [None]
    # 非公開ノートの埋め込みは、外部では中身が出ないので、その中は調べない
    private = check_publish("x.md", "![[秘密の部品]]\n", True)
    assert [i.note.path for i in private.private_embeds] == ["秘密の部品.md"] and private.private_links == ()


def test_同じノートを2回埋め込んでも中で見つけたものは1回だけ挙げる(embed_check_site):
    result = check_publish("x.md", "![[部品]]\n\n![[外枠]]\n\n![[部品]]\n", True)
    assert _via(result.private_links) == ["部品.md"] and len(result.dataview_gaps) == 1
    assert result.issue_count == 5


@pytest.mark.parametrize("body", ["![[部品]]\n", "![[外枠]]\n", "![[節つき#出す節]]\n", "![[深い1]]\n"])
def test_埋め込みの中のリンク切れは描画と公開チェックで同じ数(embed_check_site, body):
    html = render_markdown(body, published_only=True)
    result = check_publish("x.md", body, True)
    found = (len(result.private_links) + len(result.private_embeds)
             + len(result.missing_links) + len(result.missing_images))
    assert html.count('class="internal-link-broken"') == found


def test_チェックパネルは埋め込んだノートの中で見つけたものに場所を添える(embed_check_site):
    html = _get(TestClient(app, base_url=ADMIN), "部品を埋め込むページ.md", **{"as": "public"}).text
    via = (f'埋め込んだ「<a href="/view/{cache.PATH_TO_SLUG["部品.md"]}">部品</a>」'
           '<span class="publish-check-path">部品.md</span> の中')
    # 非公開リンク（本体には無し・部品の中は有り）・非公開の埋め込み・存在しないリンク・画像・Dataview に 1 つずつ
    assert html.count(via) == 5
    assert "要確認 6" in _get(TestClient(app, base_url=ADMIN), "部品を埋め込むページ.md").text


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
    monkeypatch.setattr(cache, "MEDIA_INDEX", MediaIndex(paths=frozenset({"ある画像.png"}),
                                                        by_name={"ある画像.png": "ある画像.png"}))
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
    monkeypatch.setattr(cache, "MEDIA_INDEX", MediaIndex(paths=frozenset({"ある画像.png"}),
                                                        by_name={"ある画像.png": "ある画像.png"}))
    published = {f["path"] for f in cache.GLOBAL_FILE_CACHE if f.get("published")}
    link = next(wikilinks.iter_wikilinks(src))
    target = wikilinks.classify_link(link, published)
    assert target.kind is wikilinks.LinkKind[kind]
    # 管理者向け（published_paths=None）では非公開ノートもふつうのノートとして扱う
    if kind == "PRIVATE_NOTE":
        assert wikilinks.classify_link(link, None).kind is wikilinks.LinkKind.NOTE


_CACHES_KEPT_BY_CHECK = ("GLOBAL_FILE_CACHE", "BACKLINK_CACHE", "FORWARD_LINK_CACHE", "MARKDOWN_CACHE",
                         "PATH_TO_SLUG", "SLUG_TO_PATH")


def test_公開チェックはキャッシュを書き換えない(check_site):
    # 要素の中身（各ノートの dict など）を書き換えても気づけるよう、深いコピーで比べる
    before = {name: copy.deepcopy(getattr(cache, name)) for name in _CACHES_KEPT_BY_CHECK}
    resolver = cache.NOTE_RESOLVER
    check_publish("公開ページ.md", _body_of("公開ページ.md"), True)
    check_publish("公開ページ.md", _body_of("公開ページ.md"), False)
    assert cache.NOTE_RESOLVER is resolver
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
        # 外部の人の表示の帯・切り替え（class="public-view-…"）と公開チェックを出さない。
        # public-view-links.js（F-16）の script タグは全ページで読むが、外部の人のページでは何もしない
        assert "publish-check" not in html and "要確認" not in html
        assert not re.search(r'class="[^"]*public-view', html)


def test_管理者の外部表示で非公開ノートを開くと404にせず案内を出す(check_site):
    res = _get(TestClient(app, base_url=ADMIN), "秘密.md", **{"as": "public"})
    assert res.status_code == 200
    assert get_system("S204") in res.text


def test_外部では非公開ノートは404(check_site):
    client = TestClient(app, base_url=PUBLIC)
    assert _get(client, "秘密.md").status_code == 404
    assert _get(client, "秘密.md", **{"as": "public"}).status_code == 404


# ---------- X-7: 管理者の外部表示では、ツリー・検索・プレビューも外部の人と同じ ----------

_PRIVATE_NOTES = {"秘密.md", "秘密埋め込み.md", "コード内秘密.md", "資料/非公開資料.md"}


def _tree_paths(nodes):
    """ツリー（/api/tree の応答）に出るノートのパス"""
    paths = set()
    for node in nodes:
        if node["type"] == "directory":
            paths |= _tree_paths(node["children"])
        else:
            paths.add(node["path"])
    return paths


def test_外部表示のページだけbodyに印を付ける(check_site):
    admin = TestClient(app, base_url=ADMIN)
    marked = re.compile(r'<body class="[^"]*" data-view-as="public">')
    assert marked.search(_get(admin, "公開ページ.md", **{"as": "public"}).text)
    # 非公開ノートを外部表示で開いたとき（404 にせず案内を出す画面）も外部表示
    assert marked.search(_get(admin, "秘密.md", **{"as": "public"}).text)
    assert "data-view-as" not in _get(admin, "公開ページ.md").text
    assert "data-view-as" not in _get(TestClient(app, base_url=PUBLIC), "公開ページ.md", **{"as": "public"}).text


def test_外部表示の通常の表示への導線とチェックのパネルにはdata_view_normalが付く(check_site):
    """F-16: これらのリンクは as=public を付けない対象。帯の戻る・ヘッダーの切り替え・公開チェックのパネル"""
    html = _get(TestClient(app, base_url=ADMIN), "公開ページ.md", **{"as": "public"}).text
    assert re.search(r'<a href="[^"]*" data-view-normal class="public-view-banner-back"', html)
    assert re.search(r'<a (?:id="public-view-toggle" )?href="[^"]*" data-view-normal class="public-view-toggle is-active"', html)
    assert '<section class="publish-check-panel" data-view-normal' in html


def test_管理者の外部表示のツリーは公開ノートだけ(check_site):
    admin, public = TestClient(app, base_url=ADMIN), TestClient(app, base_url=PUBLIC)
    public_tree = _tree_paths(public.get("/api/tree").json())
    assert public_tree and not public_tree & _PRIVATE_NOTES
    assert _tree_paths(admin.get("/api/tree", params={"as": "public"}).json()) == public_tree
    assert _PRIVATE_NOTES <= _tree_paths(admin.get("/api/tree").json())
    # 外部の人が as=public を付けても変わらない
    assert _tree_paths(public.get("/api/tree", params={"as": "public"}).json()) == public_tree


@pytest.mark.parametrize("q", ["秘密", "path:資料"])   # 本文の語で探す（TF-IDF）と、絞り込みだけ
def test_管理者の外部表示の検索は公開ノートだけ(check_site, q):
    admin, public = TestClient(app, base_url=ADMIN), TestClient(app, base_url=PUBLIC)

    def found(client, **params):
        return {r["path"] for r in client.get("/api/search", params={"q": q, **params}).json()}

    assert found(admin, **{"as": "public"}) == found(public) == found(public, **{"as": "public"})
    assert not found(public) & _PRIVATE_NOTES
    assert found(admin) & _PRIVATE_NOTES


def test_管理者の外部表示のプレビューは外部の人と同じ(check_site):
    admin, public = TestClient(app, base_url=ADMIN), TestClient(app, base_url=PUBLIC)

    def preview(client, path, **params):
        return client.get("/api/preview", params={"path": path, **params})

    # 非公開ノートは、外部と同じく無いノートと同じ 404
    assert preview(admin, "秘密.md", **{"as": "public"}).status_code == 404
    assert preview(admin, "秘密.md").status_code == 200
    # 公開ノートの中身も外部向けと同じ（非公開ノートへのリンクはリンク切れ、Dataview は公開ノートだけ）
    with_as = preview(admin, "公開ページ.md", **{"as": "public"}).json()
    assert with_as == preview(public, "公開ページ.md").json()
    assert "非公開資料" not in with_as["content"]
    assert "非公開資料" in preview(admin, "公開ページ.md").json()["content"]


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


def _filename_value(html):
    match = re.search(r'<input type="text" id="editor-filename" value="([^"]*)"', html)
    return match.group(1) if match else None


def test_エディタは名前を渡すと最後の部分を拡張子なしでファイル名の欄に入れる(site):
    admin = TestClient(app, base_url=ADMIN)
    assert _filename_value(admin.get("/editor", params={"name": "project-notes/old-memo.md"}).text) == "old-memo"
    assert _filename_value(admin.get("/editor", params={"name": r"a\b\  メモ .md "}).text) == "メモ"
    assert _filename_value(admin.get("/editor").text) == ""


def test_エディタはpathとnameが両方あればpathを優先して入力欄を出さない(site):
    html = TestClient(app, base_url=ADMIN).get("/editor", params={"path": "親.md", "name": "名前だけの指定"}).text
    assert _filename_value(html) is None and "名前だけの指定" not in html


def test_エディタに渡した名前はエスケープされる(site):
    html = TestClient(app, base_url=ADMIN).get("/editor", params={"name": '"><b>x'}).text
    assert "<b>x" not in html
    assert _filename_value(html) == "&#34;&gt;&lt;b&gt;x"


def test_エディタは管理者以外には名前を渡しても403(site):
    assert TestClient(app, base_url=PUBLIC).get("/editor", params={"name": "メモ"}).status_code == 403


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


def test_一覧の検索欄のtagとpathはクイックスイッチャーと同じく絞り込む(list_site):
    # B-8: 同じ検索語なら、一覧とクイックスイッチャー（/api/search）で同じノートが出る
    admin = TestClient(app, base_url=ADMIN)
    for q in ("tag:秘密タグ", "TAG:共通 path:中間"):
        listed = _titles(admin.get("/", params={"q": q}).text)
        assert listed and set(listed) == {r["title"] for r in admin.get("/api/search", params={"q": q}).json()}
    assert _titles(admin.get("/", params={"q": "tag:共通 alpha"}).text) == ["Alpha"]
    # 外部の人には、非公開ノートのタグで探しても出さない
    public = TestClient(app, base_url=PUBLIC)
    assert _titles(public.get("/", params={"q": "tag:秘密タグ"}).text) == []
    assert set(_titles(public.get("/", params={"q": "tag:共通"}).text)) == {"Alpha", "Charlie"}


def test_抜粋のリンクの閉じ忘れは次の行を巻き込まない():
    assert indexing.make_preview("[閉じ忘れ](http://a\n次の行) と [[壊れ\n本文]]") == "[閉じ忘れ](http://a 次の行) と [[壊れ 本文]]"


def test_ダッシュボードのタグ分布は件数の多い順に上位だけ(list_site, monkeypatch):
    from app.api import dashboard as dashboard_api
    monkeypatch.setattr(dashboard_api, "DASHBOARD_TOP_TAG_COUNT", 1)
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    assert "共通" in html
    assert "秘密タグ" not in html and "公開だけ" not in html


def test_ダッシュボードのヒートマップの今日はJSTで決める(list_site, monkeypatch):
    # コンテナは UTC なので、タイムゾーンなしの now() だと JST の 0〜9 時に前日になる（B-9）
    from app.api import dashboard as dashboard_api
    seen = []
    monkeypatch.setattr(dashboard_api, "build_heatmap", lambda files, now: (seen.append(now), ([], []))[1])
    TestClient(app, base_url=ADMIN).get("/dashboard")
    assert seen[0].utcoffset() == JST.utcoffset(None)



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


def test_ダッシュボードはリンク切れ孤立タグなしプロパティの誤りを数える(health_site):
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    counts = {id_: re.search(r'class="health-card-value">([^<]+)<', _health_card(html, id_)).group(1)
              for id_ in ("broken", "orphan", "untagged", "frontmatter")}
    assert counts == {"broken": "2", "orphan": "2", "untagged": "1", "frontmatter": "なし"}


def test_プロパティの誤りのカードは原因に理由を出す(health_site):
    now = time.time()
    for name, text, ago in (("壊れ.md", "---\na: 1\nb: : :\n---\n[[ハブ]]\n", 50),
                            ("文字列.md", "---\nただの文字列\n---\n[[ハブ]]\n", 40)):
        (health_site / name).write_text(text, encoding="utf-8")
        os.utime(health_site / name, (now - ago, now - ago))
    indexing.refresh_global_caches()
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    assert re.search(r'class="health-card-value">2<', _health_card(html, "frontmatter"))
    assert _health_rows(html, "frontmatter") == [
        ("文字列", "key: value の形になっていない"), ("壊れ", "YAML の書き方の誤り（3 行目）")]


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
        assert files[path]["missing_links"] == _names(check_publish(path, _body_of(path), True).missing_links)


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
    for id_ in ("broken", "orphan", "untagged", "frontmatter"):
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
    # その日が最終更新日のノートの文字数を足す（件数ではない）
    assert by_date["2026-10-08"]["chars"] == 6010 and by_date["2026-10-08"]["level"] == 3
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
    # 外部表示かどうかはパネルではなく body の data-view-as で渡す（X-7 の test_外部表示のページだけbodyに印を付ける）
    assert f'data-center="{slug}"' in html
    # d3 と描画処理は開いたときに読み込むので、ページの script には無く、読み込み先だけを渡す
    assert re.search(r'data-d3-src="/static/js/vendor/d3-[\d.]+/d3\.min\.js"', html) and 'data-render-src="/static/js/modules/graph-render.js' in html
    assert not re.search(r'<script src="[^"]*(d3\.min\.js|graph-render\.js)', html)
    assert f'href="/graph?focus={slug}"' in html
    # 深さの切り替えは config の LOCAL_GRAPH_DEPTHS から作り、先頭を選んでおく
    assert re.findall(r'name="local-graph-depth" value="(\d+)"', html) == ["1", "2"]
    assert 'value="1" id="local-graph-depth-1" checked' in html


def test_全体グラフのページはd3と描画処理を読み込む(graph_site):
    html = TestClient(app, base_url=PUBLIC).get("/graph").text
    assert re.search(r'<script src="/static/js/vendor/d3-[\d.]+/d3\.min\.js" defer>', html)
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


def test_索引の作り直しで管理者用と外部向けのグラフを作る(graph_site):
    assert "秘密B.md" in cache.LINK_GRAPH.nodes and ("中心.md", "秘密B.md") in cache.LINK_GRAPH.links
    assert "秘密B.md" not in cache.LINK_GRAPH_PUBLIC.nodes
    assert all("秘密B.md" not in link for link in cache.LINK_GRAPH_PUBLIC.links)
    assert ("中心.md", "A.md") in cache.LINK_GRAPH_PUBLIC.links


def test_記事ページとグラフのAPIは索引の作り直しで作ったグラフを使う(graph_site, monkeypatch):
    # Q-15: 表示のたびにグラフを作らない。キャッシュのグラフだけを差し替えると、つながりの数も /api/graph もそれに従う
    from app.core.graph import LinkGraph
    nodes = {p: cache.LINK_GRAPH.nodes[p] for p in ("中心.md", "孤立.md")}
    monkeypatch.setattr(cache, "LINK_GRAPH", LinkGraph(nodes, [("孤立.md", "中心.md")]))
    client = TestClient(app, base_url=ADMIN)
    assert COUNT_RE.findall(_toggle(_view(client, "中心.md"))) == ["1"]
    assert _distances(_local(client, "中心.md")) == {"中心.md": 0, "孤立.md": 1}
    # 外部向けは別のグラフ（差し替えていない）を使う
    assert COUNT_RE.findall(_toggle(_view(TestClient(app, base_url=PUBLIC), "中心.md"))) == ["2"]


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

# ---------- D-11: 768px 以下の記事ヘッダー（右上の「＋」・外部の人の表示のチップ・パンくずの省略） ----------

DIAL_TOGGLE_RE = re.compile(r'<button type="button" class="article-dial-toggle" id="article-dial-toggle".*?</button>', re.S)


def _dial_toggle(html):
    match = DIAL_TOGGLE_RE.search(html)
    assert match, "「＋」のボタンが無い"
    return match.group(0)


def test_右上のプラスはつながりとメニューをまとめaria属性を持つ(graph_site):
    html = _view(TestClient(app, base_url=ADMIN), "中心.md")
    button = _dial_toggle(html)
    assert 'aria-label="このノートの操作"' in button
    assert 'aria-expanded="false"' in button and 'aria-controls="article-dial-items"' in button
    assert 'id="article-dial-items"' in html and 'id="article-dial-menu"' in html
    # 「つながり」は今のボタンをそのまま使い（＋の中に入れる）、メニューの中身はページに 1 つだけ
    items = html[html.index('id="article-dial-items"'):html.index('id="article-dial-menu"')]
    assert 'id="local-graph-toggle"' in items
    assert html.count('id="page-menu-dropdown"') == 1 and html.count('id="copy-url-btn"') == 1
    assert html.count('id="local-graph-toggle"') == 1
    assert '<script src="/static/js/modules/article-dial.js' in html


def test_つながりのあるノートだけプラスに点を出す(graph_site):
    client = TestClient(app, base_url=ADMIN)
    assert 'class="article-dial-dot"' in _dial_toggle(_view(client, "中心.md"))
    assert "article-dial-dot" not in _dial_toggle(_view(client, "孤立.md"))
    # 外部では公開ノートだけで数える（非公開ノートにしかつながらない B2 は点を出さない）
    assert "article-dial-dot" not in _dial_toggle(_view(TestClient(app, base_url=PUBLIC), "B2.md"))


def test_外部の人のメニューはURLとPDFだけ(graph_site):
    html = _view(TestClient(app, base_url=PUBLIC), "中心.md")
    assert _dial_toggle(html)
    assert "/editor?path=" not in html
    assert 'id="copy-url-btn"' in html and 'id="export-pdf-btn"' in html


CHIP_RE = re.compile(r'<a href="([^"]+)" class="public-view-chip"')


def test_管理者の通常表示にはメタ情報の下に外部の人の表示のチップを出す(check_site):
    html = _get(TestClient(app, base_url=ADMIN), "公開ページ.md").text
    slug = cache.PATH_TO_SLUG["公開ページ.md"]
    assert CHIP_RE.findall(html) == [f"/view/{slug}?as=public"]
    chip = html[html.index('class="public-view-chip"'):]
    chip = chip[:chip.index("</a>")]
    assert "外部の人の表示" in chip and "要確認 6" in chip and "public-view-chip-chevron" in chip
    # ラベルは部品ごとの名前（600px 以下で隠すのは PC 用ボタンのラベルだけ）
    assert '<span class="public-view-chip-label">外部の人の表示</span>' in chip
    assert '<span class="public-view-toggle-label">外部の人の表示</span>' in html
    # チップはメタ情報の行の下
    assert html.index('class="view-meta"') < html.index('class="public-view-chip"')
    # PC 用の右上の切り替えボタンも今までどおり出す（どちらを見せるかは CSS）
    assert f'href="/view/{slug}?as=public" class="public-view-toggle"' in html


def test_外部の人と外部表示中にはチップを出さない(check_site):
    assert "public-view-chip" not in _get(TestClient(app, base_url=PUBLIC), "公開ページ.md").text
    assert not CHIP_RE.search(_get(TestClient(app, base_url=ADMIN), "公開ページ.md", **{"as": "public"}).text)


def test_外部表示中の帯に通常の表示へ戻るリンクを出す(check_site):
    slug = cache.PATH_TO_SLUG["公開ページ.md"]
    html = _get(TestClient(app, base_url=ADMIN), "公開ページ.md", **{"as": "public"}).text
    banner = html[html.index('class="public-view-banner"'):]
    banner = banner[:banner.index("</div>")]
    assert f'<a href="/view/{slug}" data-view-normal class="public-view-banner-back">戻る</a>' in banner
    assert "public-view-banner-back" not in _get(TestClient(app, base_url=ADMIN), "公開ページ.md").text


def _breadcrumb(html):
    m = re.search(r'<div class="breadcrumb" aria-label="パンくずリスト">(.*?)</div>', html, re.S)
    assert m, "パンくずが無い"
    return m.group(1)


def test_深いフォルダのパンくずは途中を省略できる印を持つ(site):
    path = site / "a" / "b" / "c" / "深いノート.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\npublish: true\n---\n本文\n", encoding="utf-8")
    indexing.refresh_global_caches()
    crumb = _breadcrumb(_get(TestClient(app, base_url=ADMIN), "a/b/c/深いノート.md").text)
    assert 'class="breadcrumb-ellipsis"' in crumb
    # 途中のフォルダ（a・b）だけに is-middle を付け、直前のフォルダ（c）とノート名は付けない
    assert re.findall(r'class="breadcrumb-folder( is-middle)?">([^<]+)</a>', crumb) == [
        (" is-middle", "a"), (" is-middle", "b"), ("", "c")]
    assert '<span class="breadcrumb-current" aria-current="page">深いノート</span>' in crumb


def test_フォルダが1段以下のパンくずは省略しない(check_site):
    crumb = _breadcrumb(_get(TestClient(app, base_url=ADMIN), "資料/公開資料.md").text)
    assert "breadcrumb-ellipsis" not in crumb and "is-middle" not in crumb
    assert "breadcrumb-ellipsis" not in _breadcrumb(_get(TestClient(app, base_url=ADMIN), "公開ページ.md").text)


def test_メタ情報は時刻と読了の文字を短い表示で隠せる形で出す(check_site):
    html = _get(TestClient(app, base_url=ADMIN), "公開ページ.md").text
    assert re.search(r'<span>更新 \d{4}-\d{2}-\d{2}<span class="view-meta-long"> \d{2}:\d{2}</span></span>', html)
    assert re.search(r'<span>約\d+分<span class="view-meta-long">で読了</span></span>', html)


# ---------- Q-1: ノートを読む回数 ----------

@pytest.fixture
def md_opens(monkeypatch):
    """.md を開いた回数を {ファイル名: 回数} で数える（open と Path.open。Path.read_text も Path.open を通る）"""
    counts: dict[str, int] = {}
    real_open, real_path_open = builtins.open, pathlib.Path.open

    def count(file):
        name = os.fspath(file) if isinstance(file, (str, os.PathLike)) else ""
        if name.endswith(".md"):
            counts[os.path.basename(name)] = counts.get(os.path.basename(name), 0) + 1

    def counting_open(file, *args, **kwargs):
        count(file)
        return real_open(file, *args, **kwargs)

    def counting_path_open(self, *args, **kwargs):
        count(self)
        return real_path_open(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)
    monkeypatch.setattr(pathlib.Path, "open", counting_path_open)
    return counts


def test_索引の作り直しは各ノートを1回だけ読む(check_site, md_opens, monkeypatch):
    notes = sorted(p.name for p in check_site.rglob("*.md"))
    monkeypatch.setattr(cache, "NOTE_RECORDS", {})   # 前回の記録なし（初回）
    indexing.refresh_global_caches()
    assert md_opens == {name: 1 for name in notes}


def test_変わっていないノートは2回目の作り直しで読み直さない(check_site, md_opens, monkeypatch):
    monkeypatch.setattr(cache, "NOTE_RECORDS", {})
    indexing.refresh_global_caches()
    md_opens.clear()
    indexing.refresh_global_caches()
    assert md_opens == {}


def test_管理者の記事ページは描画キャッシュが効いていれば本文を読み直さない(check_site, md_opens):
    client = TestClient(app, base_url=ADMIN)
    first = _get(client, "公開ページ.md")
    assert first.status_code == 200 and md_opens.get("公開ページ.md") == 1
    md_opens.clear()
    second = _get(client, "公開ページ.md")
    assert second.status_code == 200
    assert md_opens == {}
    # 公開チェックの結果も OGP も、キャッシュから同じものを出す
    assert second.text == first.text


# ---------- プレビューは編集中のノートをリンク元にする（B-16） ----------

def test_プレビューは編集中のノートのパスをリンク元にする(site, monkeypatch):
    from app.core.note_resolver import NoteResolver
    monkeypatch.setattr(cache, "NOTE_RESOLVER", NoteResolver([("a/同名.md", None), ("b/同名.md", None), ("b/元.md", None)]))
    monkeypatch.setattr(cache, "PATH_TO_SLUG", {"a/同名.md": "a/同名", "b/同名.md": "b/同名", "b/元.md": "b/元"})
    client = TestClient(app, base_url=ADMIN)

    def preview(**extra):
        return client.post("/api/editor/preview", json={"content": "[[同名]]", **extra}).text

    assert 'href="/view/b/同名"' in preview(path="b/元.md")
    assert 'href="/view/a/同名"' in preview()
    # 索引に無いパスは無視する
    assert 'href="/view/a/同名"' in preview(path="b/無い.md")


# ---------- 既存ノートの保存は作り直しを待たない（Q-20） ----------

def test_既存ノートの保存は索引の作り直しを待たずに返し本文はすぐ新しくなる(site, monkeypatch):
    import threading
    from app.services import note_editing

    monkeypatch.setattr(note_editing, "CONTENT_DIR", site)
    monkeypatch.setattr(note_editing, "load_config", lambda: SyncConfig())
    client = TestClient(app, base_url=ADMIN)
    assert "子の本文v1" in _view(client, "子.md")

    release, started = threading.Event(), threading.Event()
    calls = []

    def slow_refresh():
        calls.append(1)
        started.set()
        release.wait(10)

    monkeypatch.setattr(indexing, "refresh_global_caches", slow_refresh)
    old = (site / "子.md").read_text(encoding="utf-8")
    digest = client.get("/api/editor/note", params={"path": "子.md"}).json()["hash"]
    res = client.post("/api/editor/update", json={
        "path": "子.md", "content": old.replace("v1", "v2"), "base_hash": digest})
    try:
        assert res.status_code == 200 and res.json()["status"] == "success"   # 作り直しが終わっていなくても返る
        assert started.wait(5)
        assert "子の本文v2" in _view(client, "子.md")    # 記事の描画は mtime で判定するので、索引が古くても新しい
    finally:
        release.set()
        assert indexing.background_refresher.wait_idle(10)
    assert len(calls) == 1


def test_新しいノートの作成は作り直しを待ってから返す(site, monkeypatch):
    monkeypatch.setattr(editor_api, "load_config", lambda: SyncConfig())
    client = TestClient(app, base_url=ADMIN)
    res = client.post("/api/editor/save", json={"filename": "新規", "content": "新規の本文"})
    assert res.status_code == 200
    assert "新規.md" in cache.PATH_TO_SLUG      # 返った時点で索引に載っている


# ---------- 公開 → 非公開の保存だけは作り直しを待つ（外部に数秒でも見せない） ----------

def _save_note_as(client, content):
    old = (client.get("/api/editor/note", params={"path": "子.md"}).json())
    return client.post("/api/editor/update", json={"path": "子.md", "content": content, "base_hash": old["hash"]})


def _external_search(word):
    return [r["path"] for r in cache.SEARCH_INDEX.search(word, False, cache.GLOBAL_FILE_CACHE)]


@pytest.fixture
def editable_site(site, monkeypatch):
    from app.services import note_editing
    monkeypatch.setattr(note_editing, "CONTENT_DIR", site)
    monkeypatch.setattr(note_editing, "load_config", lambda: SyncConfig())
    (site / "別.md").write_text("---\npublish: true\n---\n他の本文\n", encoding="utf-8")
    indexing.refresh_global_caches()
    return site


def test_公開から非公開に変える保存は応答の時点で外部の検索に出ない(editable_site):
    client = TestClient(app, base_url=ADMIN)
    assert "子.md" in _external_search("子の本文v1")
    res = _save_note_as(client, "---\npublish: false\n---\n子の本文v1\n")
    assert res.status_code == 200
    assert "子.md" not in _external_search("子の本文v1")     # 作り直しを待ってから返したので、もう外部に出ない
    assert "子.md" not in cache.PUBLIC_MEDIA_PATHS and not any(
        f["path"] == "子.md" and f["published"] for f in cache.GLOBAL_FILE_CACHE)


@pytest.mark.parametrize("before,after", [
    ("---\npublish: false\n---\n子の本文v1\n", "---\npublish: true\n---\n子の本文v1\n"),   # 非公開 → 公開
    ("---\npublish: true\n---\n子の本文v1\n", "---\npublish: true\n---\n子の本文v2\n"),   # 本文だけの変更
    ("---\npublish: false\n---\n子の本文v1\n", "---\npublish: false\n---\n子の本文v2\n"),  # 非公開のまま
])
def test_公開から非公開以外の保存は作り直しを待たない(editable_site, monkeypatch, before, after):
    import threading
    client = TestClient(app, base_url=ADMIN)
    (editable_site / "子.md").write_text(before, encoding="utf-8")
    indexing.refresh_global_caches()
    release, started = threading.Event(), threading.Event()
    monkeypatch.setattr(indexing, "refresh_global_caches", lambda: (started.set(), release.wait(10)))
    try:
        res = _save_note_as(client, after)
        assert res.status_code == 200
        assert started.wait(5)       # 作り直しは走っているが、応答は待たずに返っている
    finally:
        release.set()
        assert indexing.background_refresher.wait_idle(10)


# ---------- F-12 プロパティ ----------

_PROP_NOTE = chr(10).join([
    "---",
    "title: 題名",
    "tags: [t1]",
    "publish: true",
    "summary: '<script>alert(1)</script> & 要約'",
    "empty:",
    "genre: dev",
    "related:",
    '  - "[[子]]"',
    '  - "[[存在しない]]"',
    "created: 2026-10-16",
    "captured_from: {cwd: /x, repo: r}",
    "---",
    "本文",
    "",
])


@pytest.fixture
def prop_site(site):
    (site / "プロパティ.md").write_text(_PROP_NOTE, encoding="utf-8")
    indexing.refresh_global_caches()
    return site


def _properties_html(html):
    m = re.search(r'<details class="note-properties".*?</details>', html, re.DOTALL)
    return m.group(0) if m else ""


def test_管理者の記事ページにタグの下へプロパティが書いた順に出る(prop_site):
    html = _get(TestClient(app, base_url=ADMIN), "プロパティ.md").text
    block = _properties_html(html)
    assert block and html.index('class="view-tags"') < html.index('class="note-properties"')
    assert re.findall(r"<dt>(.*?)</dt>", block) == ["summary", "genre", "related", "created", "captured_from"]
    assert 'class="note-properties-count">5<' in block and "外部の人には表示されません" in block
    assert "<dt>title</dt>" not in block and "<dt>tags</dt>" not in block and "<dt>publish</dt>" not in block
    assert "<dt>empty</dt>" not in block
    assert "2026-10-16" in block


def test_プロパティの値はエスケープされリンクは本文と同じ表示になる(prop_site):
    block = _properties_html(_get(TestClient(app, base_url=ADMIN), "プロパティ.md").text)
    assert "<script>" not in block and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; 要約" in block
    assert f'<a href="/view/{cache.PATH_TO_SLUG["子.md"]}" class="internal-link">子</a>' in block
    assert '<span class="internal-link-broken">存在しない</span>' in block
    assert '<span class="note-property-nested"><span>cwd</span><span>/x</span><span>repo</span><span>r</span></span>' in block


def test_外部の人と外部表示にはプロパティを出さない(prop_site):
    for client, params in ((TestClient(app, base_url=PUBLIC), {}), (TestClient(app, base_url=ADMIN), {"as": "public"})):
        html = _get(client, "プロパティ.md", **params).text
        assert "note-properties" not in html and "要約" not in html


def test_frontmatterの無い記事にプロパティの枠は出ない(prop_site):
    html = _get(TestClient(app, base_url=ADMIN), "子.md").text
    assert 'class="note-properties"' not in html


def test_frontmatterのリンクはリンク元に数える(prop_site):
    html = _get(TestClient(app, base_url=ADMIN), "子.md").text
    # 親の本文の埋め込みと、プロパティ.md の related の 2 件
    assert "リンク元 2" in html and "プロパティ" in html.split('id="backlinks"')[1]


def test_循環するfrontmatterの記事も200で開き索引も作れる(site):
    text = chr(10).join(["---", "a: &x [1, *x]", "b: &y {k: '[[子]]', self: *y}", "---", "本文", ""])
    (site / "循環.md").write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    res = _get(TestClient(app, base_url=ADMIN), "循環.md")
    assert res.status_code == 200 and "…" in _properties_html(res.text)
    assert "循環.md" in [bl["path"] for bl in cache.BACKLINK_CACHE["子.md"]]


# --- 先読み（F-15） ---

def _speculation_rules(html):
    found = re.findall(r'<script type="speculationrules">(.*?)</script>', html, re.S)
    assert len(found) == 1
    return json.loads(found[0])


# ルールは base.html に 1 つだけ。どの画面でも、どちらのポートでも同じものが入る（代表としてトップ・記事・エラー画面を見る）
@pytest.mark.parametrize("base, path", [(ADMIN, "/"), (PUBLIC, "/view/{slug}"), (ADMIN, "/view/存在しないノート")])
def test_先読みは同じサイトの記事だけを対象にする(site, base, path):
    # エラー画面（F-10）はブラウザからの読み込み（Accept: text/html）のときだけアプリの枠で出る
    html = TestClient(app, base_url=base).get(path.format(slug=cache.PATH_TO_SLUG["親.md"]),
                                              headers={"Accept": "text/html"}).text
    rules = _speculation_rules(html)
    assert list(rules) == ["prerender"], "先読みの種類は prerender だけ（ほかの種類で別の URL を足さない）"
    (rule,) = rules["prerender"]
    conditions = rule["where"]["and"]
    assert [c["href_matches"] for c in conditions if "href_matches" in c] == ["/view/*"], (
        "対象は相手のサイトを書かない相対パスの記事だけ（外部サイト・/media・/editor・/api は当たらない）")
    assert {"not": {"selector_matches": "[target=_blank], [download]"}} in conditions, (
        "新しいタブで開くリンクと download 付きは先読みしない")
    assert rule["eagerness"] == "moderate", "乗せたときだけ読む（immediate・eager でページを開いた瞬間に読まない）"


# ---------- X-3: 前回の続きから読むボタン ----------

def test_記事ページには前回の続きから読むボタンがhiddenで置かれエラー画面には無い(site):
    html = _get(TestClient(app, base_url=ADMIN), "親.md").text
    assert re.search(r'<div class="reading-resume" hidden>.*?reading-resume-go.*?aria-label="閉じる"', html, re.S)
    assert "reading-position.js" in html
    missing = TestClient(app, base_url=ADMIN).get("/view/無いノート", headers={"accept": "text/html"}).text
    assert "reading-resume" not in missing.replace("reading-position.js", "")


# ---------- X-1: 本文の #タグ ----------

@pytest.fixture
def tag_site(site):
    """本文に #タグ を書いたノートがある Vault（親.md / 子.md は消す）"""
    for name in ("親.md", "子.md"):
        (site / name).unlink()
    notes = {
        "本文タグ.md": "---\npublish: true\ntags: [先頭, 共通]\n---\n今週は #共通 と #本文だけ の話。#2024 は数字だけ。\n",
        "記号タグ.md": "---\npublish: true\ntags: ['a&b c', 'x#y']\n---\n本文\n",
        "関連.md": "---\npublish: true\n---\n#本文だけ のメモ\n",
        "数値タグ.md": "---\npublish: true\ntags: [2024]\n---\n本文\n",
        "数値だけ.md": "---\npublish: true\ntags: 2025\n---\n本文\n",
        "タグなし.md": "---\npublish: true\n---\n本文だけ\n",
        "非公開.md": "---\npublish: false\n---\n#秘密のタグ\n",
    }
    for name, text in notes.items():
        (site / name).write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    return site


def _tag_links(html):
    """記事ページのタグ欄（href, 文字）"""
    m = re.search(r'<div class="view-tags">(.*?)</div>', html, re.S)
    return re.findall(r'<a href="([^"]*)" class="view-tag">([^<]*)</a>', m.group(1)) if m else []


def test_記事ページのタグ欄にfrontmatterと本文のタグが重複なく出る(tag_site):
    html = _view(TestClient(app, base_url=ADMIN), "本文タグ.md")
    assert [t for _, t in _tag_links(html)] == ["#先頭", "#共通", "#本文だけ"]


def test_タグ欄のリンクはURLエンコードされる(tag_site):
    html = _view(TestClient(app, base_url=ADMIN), "記号タグ.md")
    assert _tag_links(html) == [("/?tag=a%26b%20c", "#a&amp;b c"), ("/?tag=x%23y", "#x#y")]


def test_タグ欄のないノートにはタグ欄を出さない(tag_site):
    assert 'class="view-tags"' not in _view(TestClient(app, base_url=ADMIN), "タグなし.md")


def test_本文のタグは記事の中でリンクになり一覧の絞り込みへ飛べる(tag_site):
    client = TestClient(app, base_url=ADMIN)
    article = _article(_view(client, "本文タグ.md"))
    assert 'href="/?tag=%E6%9C%AC%E6%96%87%E3%81%A0%E3%81%91" class="inline-tag"' in article
    assert "inline-tag" in article and article.count('class="inline-tag"') == 2   # #共通 と #本文だけ（#2024 は除く）


def test_関連記事に本文のタグが効く(tag_site):
    html = _view(TestClient(app, base_url=ADMIN), "関連.md")
    assert "関連する記事" in html
    assert re.search(r'class="related-item">本文タグ<', html)


def test_数値のタグのノートがあっても索引を作れる(tag_site):
    tags = {f["path"]: f["tags"] for f in cache.GLOBAL_FILE_CACHE}
    assert tags["数値タグ.md"] == ["2024"] and tags["数値だけ.md"] == ["2025"]
    assert _titles(TestClient(app, base_url=ADMIN).get("/", params={"tag": "2024"}).text) == ["数値タグ"]


def test_一覧の絞り込みとtag検索に本文のタグが効く(tag_site):
    client = TestClient(app, base_url=ADMIN)
    assert set(_titles(client.get("/", params={"tag": "本文だけ"}).text)) == {"本文タグ", "関連"}
    assert set(_titles(client.get("/", params={"q": "tag:本文だけ"}).text)) == {"本文タグ", "関連"}
    assert {r["path"] for r in client.get("/api/search", params={"q": "tag:本文だけ"}).json()} == {"本文タグ.md", "関連.md"}


def test_外部の人には非公開ノートの本文のタグを出さない(tag_site):
    public = TestClient(app, base_url=PUBLIC)
    assert _titles(public.get("/", params={"tag": "秘密のタグ"}).text) == []


def test_DataviewのFROMタグに本文のタグが効く(tag_site):
    out = render_markdown("```dataview\nLIST FROM #本文だけ\n```", published_only=False)
    assert "本文タグ" in out and "関連" in out and "タグなし" not in out


def test_ダッシュボードのタグなしから本文のタグのノートが外れる(tag_site):
    html = TestClient(app, base_url=ADMIN).get("/dashboard").text
    untagged = [t for t, _ in _health_rows(html, "untagged")]
    assert "関連" not in untagged and "タグなし" in untagged


# --- 一覧・全体グラフ・エラー画面の「外部の人の表示」（F-17） ---

def _view_switch(html):
    """見出しの右の切り替えボタン（<a id="public-view-toggle" …>）の開きタグ（& は戻した形）。無ければ空"""
    m = re.search(r'<a id="public-view-toggle"[^>]*>', html)
    return m.group(0).replace("&amp;", "&") if m else ""


def _banner_back(html):
    m = re.search(r'<a href="([^"]*)" data-view-normal class="public-view-banner-back">戻る</a>', html)
    return m.group(1).replace("&amp;", "&") if m else None


def test_管理者の外部の人の表示の一覧は公開ノートだけで管理者向けの物が出ない(list_site):
    html = TestClient(app, base_url=ADMIN).get("/", params={"as": "public"}).text
    assert sorted(_titles(html)) == ["Alpha", "Charlie"]
    assert "秘密タグ" not in html and "（全" not in html
    assert 'class="segmented-control"' not in html and 'class="private-mark"' not in html
    assert re.search(r'<body class="[^"]*" data-view-as="public">', html)
    assert 'class="public-view-banner"' in html and _banner_back(html) == "/"
    assert 'data-view-normal class="public-view-toggle is-active"' in _view_switch(html)


def test_外部の人の表示の一覧はvisibilityを付けても公開ノートだけ(list_site):
    html = TestClient(app, base_url=ADMIN).get("/", params={"as": "public", "visibility": "private"}).text
    assert sorted(_titles(html)) == ["Alpha", "Charlie"]


def test_外部の人の表示の一覧の中のURLはas_publicを引き継ぐ(list_site):
    html = TestClient(app, base_url=ADMIN).get("/", params={"as": "public", "tag": "共通", "q": "a"}).text
    assert '<input type="hidden" name="as" value="public">' in html
    tag_row = _tag_row(html)
    assert re.findall(r'href="([^"]+)"', tag_row) and all("as=public" in h for h in re.findall(r'href="([^"]+)"', tag_row))
    chips = re.findall(r'<a href="([^"]+)"[^>]*class="filter-chip"', html)
    assert len(chips) == 2 and all("as=public" in c for c in chips)
    assert re.search(r'href="([^"]*as=public[^"]*)"[^>]*class="filter-clear"', html)


def test_外部の人の表示の一覧のページ送りはas_publicを引き継ぐ(list_site):
    for i in range(14):
        (list_site / f"追加{i:02}.md").write_text("---\npublish: true\n---\n本文\n", encoding="utf-8")
    indexing.refresh_global_caches()
    html = TestClient(app, base_url=ADMIN).get("/", params={"as": "public"}).text
    assert re.search(r'<a href="/\?page=2&amp;as=public" class="page-link"', html)


def test_一覧の切り替えのURLと戻るのURLは今の条件を保つ(list_site):
    html = TestClient(app, base_url=ADMIN).get("/", params={"tag": "共通", "sort": "title", "as": "public"}).text
    assert _banner_back(html) == "/?tag=%E5%85%B1%E9%80%9A&sort=title"
    assert 'href="/?tag=%E5%85%B1%E9%80%9A&sort=title"' in _view_switch(html)
    normal = TestClient(app, base_url=ADMIN).get("/", params={"tag": "共通", "sort": "title"}).text
    assert 'href="/?tag=%E5%85%B1%E9%80%9A&sort=title&as=public"' in _view_switch(normal)


def test_管理者の通常の一覧には外部の人の表示のボタンだけがあり帯は無い(list_site):
    html = TestClient(app, base_url=ADMIN).get("/").text
    assert 'href="/?as=public" class="public-view-toggle"' in _view_switch(html)
    assert "外部の人の表示</span>" in html
    assert 'class="public-view-banner"' not in html and "data-view-as" not in html
    assert sorted(_titles(html)) == ["Alpha", "Bravo", "Charlie"]


@pytest.mark.parametrize("params", [{}, {"as": "public"}])
def test_外部の人の一覧はasを付けても同じで切り替えも帯も無い(list_site, params):
    html = TestClient(app, base_url=PUBLIC).get("/", params=params).text
    assert sorted(_titles(html)) == ["Alpha", "Charlie"]
    assert "data-view-as" not in html and not re.search(r'class="[^"]*public-view', html)
    assert 'name="as"' not in html and "as=public" not in _tag_row(html)


def test_管理者の全体グラフの外部の人の表示と通常の表示(graph_site):
    admin = TestClient(app, base_url=ADMIN)
    html = admin.get("/graph", params={"as": "public", "focus": "x"}).text
    assert re.search(r'<body class="[^"]*" data-view-as="public">', html)
    assert 'class="public-view-banner"' in html and _banner_back(html) == "/graph?focus=x"
    assert 'data-view-normal class="public-view-toggle is-active"' in _view_switch(html)
    normal = admin.get("/graph", params={"focus": "x"}).text
    assert 'href="/graph?focus=x&as=public" class="public-view-toggle"' in _view_switch(normal)
    assert "data-view-as" not in normal and 'class="public-view-banner"' not in normal


def test_外部の人の全体グラフはasを付けても何も出ない(graph_site):
    html = TestClient(app, base_url=PUBLIC).get("/graph", params={"as": "public"}).text
    assert "data-view-as" not in html and not re.search(r'class="[^"]*public-view', html)


def test_全体グラフのJSは外部の人の表示でも公開ノートだけのAPIを呼ぶ():
    js = (pathlib.Path(__file__).parent.parent / "static/js/modules/graph.js").read_text(encoding="utf-8")
    assert "fetch(withViewAs('/api/graph'))" in js


# --- ファイルツリーの非公開の印のテンプレート（Q-27） ---

# base.html の部品なので、記事・一覧・全体グラフ・エラー画面のどれでも同じ。管理者の通常の表示だけに置く
# （外部の人と外部の人の表示のツリーは公開ノートだけで、印を使わない）
@pytest.mark.parametrize("path", ["/", "/graph", "/view/{slug}", "/view/無いノート"])
@pytest.mark.parametrize("base, params, expected", [
    (ADMIN, {}, True),
    (ADMIN, {"as": "public"}, False),
    (PUBLIC, {}, False),
    (PUBLIC, {"as": "public"}, False),
])
def test_ツリーの非公開の印のテンプレートは管理者の通常の表示にだけ置く(site, path, base, params, expected):
    html = TestClient(app, base_url=base).get(path.format(slug=cache.PATH_TO_SLUG["親.md"]), params=params,
                                              headers={"Accept": "text/html"}).text
    assert "<body" in html, "アプリの枠で描いた画面であること（エラー画面も）"
    assert ('<template id="private-mark-template">' in html) is expected
