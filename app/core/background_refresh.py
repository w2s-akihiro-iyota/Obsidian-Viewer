"""重い処理をバックグラウンドで 1 本だけ走らせる（Q-20。索引の作り直し用）"""
import logging
import threading
from typing import Callable

logger = logging.getLogger("app.background_refresh")


class BackgroundRefresher:
    """
    task を別スレッドで走らせる。同時に 1 本だけで、走っている間に来た依頼は終わったあとの 1 回にまとめる

    何回依頼しても、依頼が落ち着いたあとに 1 回で済む。task の失敗はログに残し、次の依頼は受け付ける。
    """

    def __init__(self, task: Callable[[], None], name: str = "background-refresh"):
        self._task = task
        self._name = name
        self._lock = threading.Lock()
        self._running = False
        self._pending = False
        self._idle = threading.Event()
        self._idle.set()

    def request(self) -> None:
        """作り直しを頼む（待たずに戻る）"""
        with self._lock:
            if self._running:
                self._pending = True
                return
            self._running = True
            self._idle.clear()
        threading.Thread(target=self._loop, name=self._name, daemon=True).start()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """走っているものも、まとめられた次の 1 回も終わるまで待つ（終わっていれば True）"""
        return self._idle.wait(timeout)

    def _loop(self) -> None:
        while True:
            try:
                self._task()
            except Exception:
                logger.exception("Background refresh failed.")
            with self._lock:
                if self._pending:
                    self._pending = False
                    continue
                self._running = False
                self._idle.set()
                return
