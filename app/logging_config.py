"""ロギング設定モジュール"""
import logging
import sys


def setup_logging() -> None:
    """アプリケーション全体のロギングを初期化する。Docker環境向けにstdout出力。"""
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.flush = sys.stdout.flush

    root = logging.getLogger("app")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # 親ロガーへの伝播を抑制（二重出力防止）
    root.propagate = False
