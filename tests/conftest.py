"""テスト全体の共通設定"""
import pytest

from app import cache
from app.core import sync_history


@pytest.fixture(autouse=True)
def _isolate_sync_history(tmp_path, monkeypatch):
    """同期の記録（F-7）を tmp_path に書かせる（本物の app/sync_history.json に混ぜない）"""
    monkeypatch.setattr(sync_history, "SYNC_HISTORY_FILE", tmp_path / "sync_history.json")


def cache_names() -> list[str]:
    """app/cache.py のキャッシュの名前（大文字の変数）。名前を書き並べないので、キャッシュを足してもここは直さない"""
    return [name for name in vars(cache) if name.isupper()]


@pytest.fixture
def isolated_caches(monkeypatch):
    """
    app/cache.py のキャッシュを、テストが終わったら元の値に戻す（Q-25）

    索引を作り直すテスト（refresh_global_caches）は、この fixture を使う。作り直しで差し替えたキャッシュを、ほかのテストに残さない。
    """
    for name in cache_names():
        monkeypatch.setattr(cache, name, getattr(cache, name))
