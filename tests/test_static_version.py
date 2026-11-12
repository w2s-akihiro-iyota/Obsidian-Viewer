"""静的ファイルの版（?v=）の契約テスト（Q-5）

- 版はファイルの中身から作る。中身が変われば版も変わり、再起動は要らない。同じ中身なら同じ版
- ファイルが無い・static の外を指すときは、版を付けずに返す（ページは描ける）
- CSS は style.css の @import の順に 1 つずつ読み込む
- テンプレートに手書きの版は残さない。ページが読み込む CSS・JS には、全部中身から作った版が付く
"""
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import STATICS_DIR, TEMPLATES_DIR
from app.main import app
from app.utils import static_version

BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
VERSIONED = re.compile(r'(?:src|href)="(/static/[^"]+)"')


@pytest.fixture
def static_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(static_version, "STATICS_DIR", tmp_path)
    monkeypatch.setattr(static_version, "_versions", {})
    (tmp_path / "js").mkdir()
    return tmp_path


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:static_version.VERSION_LENGTH]


# --- 版の作り方 ---

def test_版はファイルの中身から作る(static_dir):
    (static_dir / "js" / "a.js").write_text("console.log(1);", encoding="utf-8")
    assert static_version.static_url("js/a.js") == f"/static/js/a.js?v={_hash('console.log(1);')}"
    # 先頭の /static/ は付けても同じ
    assert static_version.static_url("/static/js/a.js") == static_version.static_url("js/a.js")


def test_中身が変われば版も変わる(static_dir):
    target = static_dir / "js" / "a.js"
    target.write_text("console.log(1);", encoding="utf-8")
    before = static_version.static_url("js/a.js")
    target.write_text("console.log(22);", encoding="utf-8")
    after = static_version.static_url("js/a.js")
    assert before != after and after.endswith(_hash("console.log(22);"))


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
