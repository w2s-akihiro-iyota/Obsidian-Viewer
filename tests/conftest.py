"""テスト全体の共通設定"""
import pytest

from app.core import sync_history


@pytest.fixture(autouse=True)
def _isolate_sync_history(tmp_path, monkeypatch):
    """同期の記録（F-7）を tmp_path に書かせる（本物の app/sync_history.json に混ぜない）"""
    monkeypatch.setattr(sync_history, "SYNC_HISTORY_FILE", tmp_path / "sync_history.json")
