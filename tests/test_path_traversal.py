"""パストラバーサル防止の契約テスト

- /api/preview（app/api/content.py）: path に `..` を含むものと、先頭が `/` のものは 400
- /api/editor/save（app/api/editor.py）: ファイル名に `..` `/` `\\` と Windows で使えない文字を含むものは 400（E202）

どちらも CONTENT_DIR の外を読み書きさせないための入口の検査。
"""
import pytest
from fastapi.testclient import TestClient

from app import cache
from app.api import content as content_api
from app.api import editor as editor_api
from app.main import app
from app.utils.messages import get_error

ADMIN = "http://localhost:8001"


@pytest.fixture
def content_dir(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    (content / "公開.md").write_text("---\npublish: true\n---\n本文\n", encoding="utf-8")
    (tmp_path / "外.md").write_text("---\npublish: true\n---\nCONTENT_DIR の外\n", encoding="utf-8")
    monkeypatch.setattr(content_api, "CONTENT_DIR", content)
    monkeypatch.setattr(editor_api, "CONTENT_DIR", content)
    monkeypatch.setattr(cache, "SLUG_TO_PATH", {})
    monkeypatch.setattr(cache, "FILE_NAME_CACHE", {})
    return content


@pytest.fixture
def client():
    return TestClient(app, base_url=ADMIN)


# ---------- /api/preview ----------

def test_プレビューはCONTENT_DIRの中のノートを返す(content_dir, client):
    res = client.get("/api/preview", params={"path": "公開.md"})
    assert res.status_code == 200
    assert "本文" in res.json()["content"]


@pytest.mark.parametrize("path", [
    "../外.md",
    "sub/../../外.md",
    "..",
    "..\\外.md",
    "/etc/passwd",
    "/公開.md",
])
def test_プレビューはドット2つと先頭のスラッシュを400にする(content_dir, client, path):
    res = client.get("/api/preview", params={"path": path})
    assert res.status_code == 400
    assert "CONTENT_DIR の外" not in res.text


def test_いまはファイル名の中のドット2つも400にする(content_dir, client):
    # `..` を含むかの文字列判定なので、「メモ..md」のような名前のノートもプレビューできない（いまの振る舞い）
    (content_dir / "メモ..md").write_text("---\npublish: true\n---\nx\n", encoding="utf-8")
    assert client.get("/api/preview", params={"path": "メモ..md"}).status_code == 400


# ---------- /api/editor/save ----------

@pytest.mark.parametrize("filename", [
    "../外",
    "..",
    "a..b",
    "sub/ノート",
    "/etc/passwd",
    "sub\\ノート",
    "C:\\temp\\x",
])
def test_エディタの保存はドット2つとスラッシュとバックスラッシュを400にする(content_dir, client, filename):
    res = client.post("/api/editor/save", json={"filename": filename, "content": "本文"})
    assert res.status_code == 400
    assert res.json()["message"] == get_error("E202")
    assert sorted(p.name for p in content_dir.parent.rglob("*")) == ["content", "公開.md", "外.md"]


@pytest.mark.parametrize("ch", list('<>:"|?*'))
def test_エディタの保存はWindowsで使えない文字を400にする(content_dir, client, ch):
    res = client.post("/api/editor/save", json={"filename": f"名前{ch}", "content": "本文"})
    assert res.status_code == 400
    assert res.json()["message"] == get_error("E202")


def test_エディタの保存は外部ポートから403(content_dir):
    res = TestClient(app, base_url="http://localhost:8000").post(
        "/api/editor/save", json={"filename": "../外", "content": "本文"})
    assert res.status_code == 403
