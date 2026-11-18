"""静的ファイルの版（?v=）の契約テスト（Q-5・Q-34・Q-35）

- 版はファイルの中身から作る。同じ中身なら同じ版
- 版は最初に使ったときに 1 回だけ作り、プロセスが終わるまで覚える（2 回目からはファイルを見に行かない。
  中身を変えたら再起動で作り直す。Q-34）
- ファイルが無い・static の外を指すときは、版を付けずに返す（ページは描ける）
- CSS は style.css の @import の順に 1 つずつ読み込む
- テンプレートに手書きの版は残さない。ページが読み込む CSS・JS には、全部中身から作った版が付く
- 版付きの URL（?v=）は、ブラウザに長く覚えさせる（Cache-Control: immutable。Q-35）。版の付かない URL には付けない
"""
import contextlib
import hashlib
import io
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import STATICS_DIR, TEMPLATES_DIR
from app.main import app
from app.utils import static_version

BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
VERSIONED = re.compile(r'(?:src|href)="(/static/[^"]+)"')


def _forget_versions():
    """覚えた版を捨てる（再起動の代わり）"""
    static_version.static_url.cache_clear()
    static_version.stylesheet_urls.cache_clear()


@pytest.fixture
def static_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(static_version, "STATICS_DIR", tmp_path)
    _forget_versions()
    (tmp_path / "js").mkdir()
    yield tmp_path
    _forget_versions()  # 一時フォルダの版を、ほかのテストに残さない


def _no_file_access(*args, **kwargs):
    raise AssertionError("ページを返すときにファイルを見に行った")


@contextlib.contextmanager
def _file_access_forbidden():
    """この中では、ファイルの状態を調べる・開くと落ちる（stat・lstat・resolve・is_file・read_* はどれもここを通る）。
    落ちたときも pytest が失敗を書き出す前に元へ戻すよう、fixture ではなく with で囲む"""
    with pytest.MonkeyPatch.context() as m:
        for name in ("stat", "lstat"):
            m.setattr(os, name, _no_file_access)
        m.setattr(io, "open", _no_file_access)
        yield


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:static_version.VERSION_LENGTH]


# --- 版の作り方 ---

def test_版はファイルの中身から作る(static_dir):
    (static_dir / "js" / "a.js").write_text("console.log(1);", encoding="utf-8")
    assert static_version.static_url("js/a.js") == f"/static/js/a.js?v={_hash('console.log(1);')}"
    # 先頭の /static/ は付けても同じ
    assert static_version.static_url("/static/js/a.js") == static_version.static_url("js/a.js")


def test_一度作った版は再起動まで変わらない(static_dir):
    target = static_dir / "js" / "a.js"
    target.write_text("console.log(1);", encoding="utf-8")
    before = static_version.static_url("js/a.js")
    target.write_text("console.log(22);", encoding="utf-8")
    assert static_version.static_url("js/a.js") == before
    _forget_versions()
    assert static_version.static_url("js/a.js").endswith(_hash("console.log(22);"))


def test_2回目からはファイルを見に行かない(static_dir):
    (static_dir / "js" / "a.js").write_text("console.log(1);", encoding="utf-8")
    (static_dir / "css" / "modules").mkdir(parents=True)
    (static_dir / "css" / "modules" / "a.css").write_text(".a{}", encoding="utf-8")
    (static_dir / "css" / "style.css").write_text("@import url('modules/a.css');\n", encoding="utf-8")
    first = (static_version.static_url("js/a.js"), static_version.static_url("js/none.js"), static_version.stylesheet_urls())
    with _file_access_forbidden():
        again = (static_version.static_url("js/a.js"), static_version.static_url("js/none.js"), static_version.stylesheet_urls())
    assert again == first


def test_同じ中身なら別のファイルでも同じ版(static_dir):
    for name in ("a.js", "b.js"):
        (static_dir / "js" / name).write_text("same", encoding="utf-8")
    assert static_version.static_url("js/a.js").split("?v=")[1] == static_version.static_url("js/b.js").split("?v=")[1]


@pytest.mark.parametrize("rel", ["js/none.js", "../secret.txt", "js"])
def test_無いファイルやstaticの外には版を付けない(static_dir, rel):
    (static_dir.parent / "secret.txt").write_text("x", encoding="utf-8")
    url = static_version.static_url(rel)
    assert "?v=" not in url and url == f"/static/{rel}"


def test_CSSはstyle_cssのimportの順に並べる(static_dir):
    (static_dir / "css" / "modules").mkdir(parents=True)
    for name in ("b", "a", "c"):
        (static_dir / "css" / "modules" / f"{name}.css").write_text(f".{name}{{}}", encoding="utf-8")
    (static_dir / "css" / "style.css").write_text(
        "/* @import の順に読む */\n@import url('modules/b.css');\n@import url(\"modules/a.css\");\n@import url(modules/c.css);\n",
        encoding="utf-8")
    urls = static_version.stylesheet_urls()
    assert [u.split("?v=")[0] for u in urls] == [f"/static/css/modules/{n}.css" for n in ("b", "a", "c")]
    assert all(re.search(r"\?v=[0-9a-f]{10}$", u) for u in urls)


# --- 実際のテンプレートとページ ---

def test_テンプレートに手書きの版を残さない():
    found = [f"{p.relative_to(TEMPLATES_DIR)}: {m.group(0)}"
             for p in TEMPLATES_DIR.rglob("*.html")
             for m in re.finditer(r"/static/[^\"'\s]+\?v=", p.read_text(encoding="utf-8"))]
    assert found == []


def test_style_cssには版を書かない():
    text = (STATICS_DIR / "css" / "style.css").read_text(encoding="utf-8")
    assert "@import" in text and "?v=" not in re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_ページが読み込むCSSとJSには中身から作った版が付く():
    # エラー画面は base.html をそのまま使うので、ノートが無くても描ける
    html = TestClient(app, base_url="http://localhost:8001").get("/settingz", headers=BROWSER).text
    urls = VERSIONED.findall(html)
    modules = [u for u in urls if u.startswith(("/static/css/modules/", "/static/js/modules/"))]
    assert len(modules) >= 20
    for url in modules:
        path, _, version = url.partition("?v=")
        file = STATICS_DIR / path.removeprefix("/static/")
        assert file.is_file(), url
        assert version == hashlib.sha256(file.read_bytes()).hexdigest()[:static_version.VERSION_LENGTH], url
    # CSS は style.css の @import の順
    css = [u.split("?v=")[0] for u in urls if u.startswith("/static/css/modules/")]
    imports = re.findall(r"@import url\('([^']+)'\)", (STATICS_DIR / "css" / "style.css").read_text(encoding="utf-8"))
    assert css == [f"/static/css/{href}" for href in imports]


# --- ブラウザに覚えさせる長さ（Q-35） ---

IMMUTABLE = "public, max-age=31536000, immutable"


def test_版付きのURLはブラウザに長く覚えさせる():
    client = TestClient(app)
    url = static_version.static_url("js/modules/core.js")
    assert "?v=" in url
    resp = client.get(url)
    assert resp.status_code == 200 and resp.headers.get("cache-control") == IMMUTABLE
    # 中身が同じか確かめ直す応答（304）も同じ
    again = client.get(url, headers={"If-None-Match": resp.headers["etag"]})
    assert again.status_code == 304 and again.headers.get("cache-control") == IMMUTABLE


@pytest.mark.parametrize("url", ["/static/js/modules/core.js", "/static/images/logo.png", "/static/js/vendor/htmx-1.9.10/htmx.min.js"])
def test_版の付かないURLは長く覚えさせない(url):
    resp = TestClient(app).get(url)
    assert resp.status_code == 200 and "immutable" not in resp.headers.get("cache-control", "")


def test_無いファイルは版が付いていても覚えさせない():
    resp = TestClient(app).get("/static/js/none.js?v=0123456789")
    assert resp.status_code == 404 and "immutable" not in resp.headers.get("cache-control", "")
