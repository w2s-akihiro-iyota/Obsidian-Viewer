"""エラー画面（F-10）の契約テスト

- ブラウザでページを開いたとき（Accept に text/html）だけ、JSON の代わりにエラー画面を返す。ステータスは変えない
- API（/api/）・添付（/media/・/static/）・HTMX の読み込み（HX-Request）は今まで通り JSON
- 外部の人が非公開ノートを開いたときは、無いノートと同じ 404（存在を知らせない）
- 管理者にだけ、開こうとしたパスと次の一手（新規作成・同期）を出す
- 500 は例外の中身を外に出さない。エラー画面の描画まで失敗したら素の HTML で返す
"""
import pytest
from fastapi.testclient import TestClient

from app import cache
from app.api import content as content_api
from app.api import errors as errors_api
from app.api import editor as editor_api
from app.core import indexing
from app.main import app
from app.services import wikilinks
from app.utils.messages import get_error

ADMIN = "http://localhost:8001"
PUBLIC = "http://localhost:8000"
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


@pytest.fixture
def site(tmp_path, monkeypatch):
    for name in ("GLOBAL_FILE_CACHE", "GLOBAL_FILE_TREE_CACHE", "GLOBAL_FILE_TREE_CACHE_PUBLIC", "MEDIA_INDEX",
                 "PUBLIC_MEDIA_PATHS", "MARKDOWN_CACHE", "FILE_NAME_CACHE", "BACKLINK_CACHE", "FORWARD_LINK_CACHE", "SEARCH_INDEX",
                 "SLUG_TO_PATH", "PATH_TO_SLUG"):
        monkeypatch.setattr(cache, name, getattr(cache, name))
    for module in (content_api, editor_api, indexing, wikilinks):
        monkeypatch.setattr(module, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(indexing, "MEDIA_DIR", tmp_path.parent / f"{tmp_path.name}-media")
    (tmp_path / "公開.md").write_text("---\npublish: true\n---\n公開の本文\n", encoding="utf-8")
    (tmp_path / "秘密.md").write_text("---\npublish: false\n---\n秘密の本文\n", encoding="utf-8")
    indexing.refresh_global_caches()
    return tmp_path


def _slug(path):
    return cache.PATH_TO_SLUG[path]


def _page(res):
    """エラー画面の中身（ヘッダーやモーダルを除いた main の部分）"""
    start = res.text.index('class="error-page"')
    return res.text[start:res.text.index("</main>", start)]


# --- ブラウザで開いたページはエラー画面 ---

def test_無いノートはエラー画面で404(site):
    res = TestClient(app, base_url=PUBLIC).get("/view/無いノート", headers=BROWSER)
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("text/html")
    assert get_error("E301") in _page(res)
    # アプリの枠の中に出す（ヘッダーと検索が残る）
    assert '<header>' in res.text and 'id="search-modal"' in res.text


def test_存在しないURLはページが見つからない画面で404(site):
    res = TestClient(app, base_url=PUBLIC).get("/settingz", headers=BROWSER)
    assert res.status_code == 404
    assert get_error("E303") in _page(res)


def test_外部から管理者専用の画面を開くと403の画面(site):
    for path in ("/dashboard", "/editor"):
        res = TestClient(app, base_url=PUBLIC).get(path, headers=BROWSER)
        assert res.status_code == 403
        assert get_error("E305") in _page(res)


def test_エラー画面はHTMLとして安全に組み立てる(site):
    # URL に入れた文字列はエスケープして出す（管理者にだけ出すパスでも）
    res = TestClient(app, base_url=ADMIN).get("/view/%3Cscript%3Ealert(1)%3C%2Fscript%3E", headers=BROWSER)
    assert res.status_code == 404
    assert "<script>alert(1)</script>" not in res.text
    assert "&lt;script&gt;" in _page(res)


# --- 非公開ノートは 404 にそろえる ---

def test_外部の人には非公開ノートと無いノートが同じに見える(site):
    client = TestClient(app, base_url=PUBLIC)
    private = client.get(f"/view/{_slug('秘密.md')}", headers=BROWSER)
    missing = client.get("/view/無いノート", headers=BROWSER)
    assert private.status_code == missing.status_code == 404
    assert _page(private) == _page(missing)
    assert "秘密の本文" not in private.text


def test_外部の人には非公開ノートのJSONも無いノートと同じ404(site):
    client = TestClient(app, base_url=PUBLIC)
    private = client.get(f"/view/{_slug('秘密.md')}")
    missing = client.get("/view/無いノート")
    assert private.status_code == missing.status_code == 404
    assert private.json() == missing.json()


def test_外部の人には実ファイルのパスで開いても非公開ノートを飛ばさず404(site):
    client = TestClient(app, base_url=PUBLIC)
    private = client.get("/view/秘密.md", headers=BROWSER, follow_redirects=False)
    missing = client.get("/view/無いノート.md", headers=BROWSER, follow_redirects=False)
    assert private.status_code == missing.status_code == 404
    assert _page(private) == _page(missing)
    # 公開ノートと管理者は今まで通りスラッグの URL へ飛ぶ
    assert client.get("/view/公開.md", follow_redirects=False).status_code == 301
    assert TestClient(app, base_url=ADMIN).get("/view/秘密.md", follow_redirects=False).status_code == 301


def test_プレビューにフォルダを渡すと無いノートと同じ404(site):
    (site / "資料").mkdir()
    res = TestClient(app, base_url=ADMIN).get("/api/preview", params={"path": "資料"})
    assert res.status_code == 404 and res.json() == {"detail": "File not found"}


def test_外部の人には非公開ノートのプレビューも404(site):
    client = TestClient(app, base_url=PUBLIC)
    private = client.get("/api/preview", params={"path": "秘密.md"})
    missing = client.get("/api/preview", params={"path": "無いノート.md"})
    assert private.status_code == missing.status_code == 404
    assert private.json() == missing.json()


def test_管理者は非公開ノートを開ける(site):
    res = TestClient(app, base_url=ADMIN).get(f"/view/{_slug('秘密.md')}", headers=BROWSER)
    assert res.status_code == 200 and "秘密の本文" in res.text


# --- 管理者にだけ出すもの ---

def test_管理者には開こうとしたパスと次の一手を出す(site):
    res = TestClient(app, base_url=ADMIN).get("/view/project-notes/old-memo", headers=BROWSER)
    page = _page(res)
    assert res.status_code == 404
    assert "project-notes/old-memo" in page
    assert 'href="/editor"' in page and "data-open-sync" in page


def test_外部の人にはパスも管理者向けの操作も出さない(site):
    page = _page(TestClient(app, base_url=PUBLIC).get("/view/project-notes/old-memo", headers=BROWSER))
    assert "project-notes/old-memo" not in page
    assert 'href="/editor"' not in page and "data-open-sync" not in page


# --- ページ以外は今まで通り JSON ---

@pytest.mark.parametrize("path", ["/api/graph?center=無いノート", "/api/no-such-api"])
def test_APIはブラウザのAcceptでもJSONのまま(site, path):
    res = TestClient(app, base_url=ADMIN).get(path, headers=BROWSER)
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/json")


def test_添付の404はエラー画面にしない(site):
    res = TestClient(app, base_url=PUBLIC).get("/media/無い画像.png", headers=BROWSER)
    assert res.status_code == 404
    assert not res.headers["content-type"].startswith("text/html")


def test_HTMXの読み込みはJSONのまま(site):
    res = TestClient(app, base_url=PUBLIC).get("/view/無いノート", headers={**BROWSER, "HX-Request": "true"})
    assert res.status_code == 404
    assert res.json() == {"detail": "File not found"}


def test_AcceptにHTMLが無ければJSONのまま(site):
    res = TestClient(app, base_url=PUBLIC).get("/view/無いノート")
    assert res.status_code == 404 and res.json() == {"detail": "File not found"}


# --- 500 ---

def _boom(*args, **kwargs):
    raise RuntimeError("secret-stack-detail")


def test_想定外のエラーは500の画面で中身を出さない(site, monkeypatch):
    monkeypatch.setattr(content_api, "build_note_list", _boom)
    for base in (PUBLIC, ADMIN):
        res = TestClient(app, base_url=base, raise_server_exceptions=False).get("/", headers=BROWSER)
        assert res.status_code == 500
        assert get_error("E309") in _page(res)
        assert "secret-stack-detail" not in res.text


def test_想定外のエラーはAPIにはHTMLを返さない(site, monkeypatch):
    monkeypatch.setattr(content_api, "build_note_list", _boom)
    res = TestClient(app, base_url=PUBLIC, raise_server_exceptions=False).get("/")
    assert res.status_code == 500
    assert not res.headers["content-type"].startswith("text/html")
    assert "secret-stack-detail" not in res.text


def test_エラー画面の描画に失敗しても素のHTMLで返す(site, monkeypatch):
    monkeypatch.setattr(content_api, "build_note_list", _boom)
    monkeypatch.setattr(errors_api.templates, "TemplateResponse", _boom)
    res = TestClient(app, base_url=PUBLIC, raise_server_exceptions=False).get("/", headers=BROWSER)
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("text/html")
    assert get_error("E309") in res.text
    assert "secret-stack-detail" not in res.text
