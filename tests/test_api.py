"""API の契約テスト（TestClient。httpx は requirements-dev.txt）

- 記事ページのキャッシュは、埋め込んだノートの更新・削除で作り直す（F-4）
- 保留した削除の API は管理者だけ。同期中は 409（B-2 / B-4）
- 新規ノートの保存は、Vault に書けなければビューア側にも書かない（B-2 の削除で消えないように）
"""
import os
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
