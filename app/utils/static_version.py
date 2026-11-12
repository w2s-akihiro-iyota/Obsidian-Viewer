"""静的ファイルの URL に、中身から作った版（?v=）を付ける（Q-5）

前はテンプレートと style.css に `?v=20261111f` のような版を手で書き、ファイルを直すたびに書き換えていた。
書き換えを忘れると、ブラウザが古い CSS・JS を使い続ける。

- static_url("js/modules/core.js") → "/static/js/modules/core.js?v=<中身のハッシュの先頭 10 文字>"
  ファイルが変わったか（更新時刻・大きさ）を見て、変わったときだけハッシュを作り直す。再起動は要らない
- stylesheet_urls() → style.css の @import の順に、各 CSS の版付き URL を並べる
  テンプレートはこれを <link> で 1 つずつ読み込む。style.css は読み込む順の一覧として残す（@import の URL には版を付けない）
"""
import hashlib
import logging
import re
from pathlib import Path

from app.config import STATICS_DIR

logger = logging.getLogger("app.static_version")

VERSION_LENGTH = 10
STYLESHEET_INDEX = "css/style.css"
_IMPORT_RE = re.compile(r"""@import\s+url\(\s*['"]?([^'")?]+)""")

# 実ファイルのパス → (更新時刻, 大きさ, 版)
_versions: dict[Path, tuple[int, int, str]] = {}


def _resolve(rel: str) -> Path | None:
    """STATICS_DIR の下の実ファイルを返す。無い・外を指すときは None"""
    try:
        root = STATICS_DIR.resolve()
        path = (root / rel).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def _version(path: Path) -> str:
    stat = path.stat()
    cached = _versions.get(path)
    if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
        return cached[2]
    version = hashlib.sha256(path.read_bytes()).hexdigest()[:VERSION_LENGTH]
    _versions[path] = (stat.st_mtime_ns, stat.st_size, version)
    return version


def static_url(rel: str) -> str:
    """static/ からの相対パス（先頭の /static/ は付けても付けなくてもよい）を、版付きの URL にする。
    ファイルが無いときは版を付けずに返し、ログに残す（ページは描けるようにする）"""
    rel = rel.removeprefix("/static/").lstrip("/")
    path = _resolve(rel)
    try:
        if path is not None:
            return f"/static/{rel}?v={_version(path)}"
    except OSError:  # 調べている間に消えた・読めない
        pass
    logger.warning("static_url: ファイルが見つからないので版を付けない: %s", rel)
    return f"/static/{rel}"


def stylesheet_urls() -> list[str]:
    """style.css の @import の順に、読み込む CSS の版付き URL を返す"""
    index = _resolve(STYLESHEET_INDEX)
    if index is None:
        logger.warning("stylesheet_urls: %s が見つからない", STYLESHEET_INDEX)
        return []
    base = Path(STYLESHEET_INDEX).parent
    return [static_url((base / href).as_posix()) for href in _IMPORT_RE.findall(index.read_text(encoding="utf-8"))]
