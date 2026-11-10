"""設定の保存（app/api/sync.py の api_save_sync_settings）の契約テスト

F-11: 追加の同期元（extra_sources）を行ごとに検証する。
- src が空・フォルダが無い → errors["extra-src-{行}"]
- 置き場所が使えない・ほかの行と重複・元フォルダの直下に同じ名前 → errors["extra-dest-{行}"]
- 同期が有効なときだけ検証する。exclude は正規化して保存する
"""
import pytest
from fastapi.testclient import TestClient

from app.api import sync as sync_api
from app.main import app
from app.models.sync import SyncConfig

ADMIN = "http://localhost:8001"
PUBLIC = "http://localhost:8000"


@pytest.fixture
def saved(monkeypatch):
    """保存を tmp に向けず、呼ばれた設定だけ集める（本物の server_config.yaml は書かない）"""
    configs: list[SyncConfig] = []
    monkeypatch.setattr(sync_api, "save_config", configs.append)
    return configs


@pytest.fixture
def dirs(tmp_path):
    notes, wiki = tmp_path / "notes", tmp_path / "wiki"
    notes.mkdir()
    wiki.mkdir()
    return notes, wiki


def _post(notes, extras, **kwargs):
    body = {"sync_enabled": True, "content_src": str(notes), "extra_sources": extras, **kwargs}
    return TestClient(app, base_url=ADMIN).post("/api/sync/save", json=body)


def test_正しい追加の同期元は保存し_excludeを正規化する(saved, dirs):
    notes, wiki = dirs
    res = _post(notes, [{"src": str(wiki), "dest": "llm-wiki", "exclude": [" raw/ ", "", "raw", "\\a\\b\\"]}])
    assert res.status_code == 200 and res.json()["status"] == "success"
    extra = saved[0].extra_sources[0]
    assert (extra.src, extra.dest, extra.exclude) == (str(wiki), "llm-wiki", ["raw", "a/b"])


def test_追加の同期元が無くても保存できる(saved, dirs):
    notes, _ = dirs
    res = TestClient(app, base_url=ADMIN).post("/api/sync/save", json={"sync_enabled": True, "content_src": str(notes)})
    assert res.status_code == 200 and saved[0].extra_sources == []


@pytest.mark.parametrize("src", ["", "/nowhere/at/all"])
def test_srcが空かフォルダが無ければ行のエラー(saved, dirs, src):
    notes, wiki = dirs
    res = _post(notes, [{"src": str(wiki), "dest": "ok"}, {"src": src, "dest": "wiki2"}])
    assert res.status_code == 400
    assert list(res.json()["errors"]) == ["extra-src-1"]
    assert saved == []


@pytest.mark.parametrize("dest", ["", "a/b", ".hidden", "a:b", "samples"])
def test_使えない置き場所は行のエラー(saved, dirs, dest):
    notes, wiki = dirs
    res = _post(notes, [{"src": str(wiki), "dest": dest}])
    assert res.status_code == 400 and list(res.json()["errors"]) == ["extra-dest-0"]
    assert saved == []


def test_ほかの行と重複する置き場所は後ろの行のエラー(saved, dirs):
    notes, wiki = dirs
    res = _post(notes, [{"src": str(wiki), "dest": "wiki"}, {"src": str(wiki), "dest": "wiki"}])
    assert res.status_code == 400 and list(res.json()["errors"]) == ["extra-dest-1"]


def test_元フォルダの直下に同じ名前があれば行のエラー(saved, dirs):
    notes, wiki = dirs
    (notes / "wiki").mkdir()
    res = _post(notes, [{"src": str(wiki), "dest": "wiki"}])
    assert res.status_code == 400 and list(res.json()["errors"]) == ["extra-dest-0"]


def test_同期が無効なら検証しない(saved, dirs):
    notes, _ = dirs
    res = _post(notes, [{"src": "", "dest": "a/b"}], sync_enabled=False)
    assert res.status_code == 200 and len(saved) == 1


def test_管理者だけが保存できる(saved, dirs):
    notes, _ = dirs
    res = TestClient(app, base_url=PUBLIC).post("/api/sync/save", json={"content_src": str(notes)})
    assert res.status_code == 403 and saved == []
