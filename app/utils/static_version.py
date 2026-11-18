"""静的ファイルの URL に、中身から作った版（?v=）を付ける（Q-5・Q-34・Q-35）

前はテンプレートと style.css に `?v=20261111f` のような版を手で書き、ファイルを直すたびに書き換えていた。
書き換えを忘れると、ブラウザが古い CSS・JS を使い続ける。

- static_url("js/modules/core.js") → "/static/js/modules/core.js?v=<中身のハッシュの先頭 10 文字>"
- stylesheet_urls() → style.css の @import の順に、各 CSS の版付き URL を並べる
  テンプレートはこれを <link> で 1 つずつ読み込む。style.css は読み込む順の一覧として残す（@import の URL には版を付けない）
- 版は、起動してから最初に使ったときに 1 回だけ作り、プロセスが終わるまで覚える（Q-34）
  前は呼ぶたびにファイルの更新時刻を見ていたが、Docker のマウント越しでは 1 回数 ms かかり、
  1 ページ（約 45 ファイル）で 1 秒以上待たせていた。CSS・JS を直したら再起動で版を作り直す
- 版付きの URL は中身が変わらないので、ブラウザに長く覚えさせる（VersionedStaticFiles。Q-35）
"""
import hashlib
import logging
import re
from functools import cache
from pathlib import Path
from urllib.parse import parse_qs

from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app.config import STATICS_DIR

logger = logging.getLogger("app.static_version")

VERSION_LENGTH = 10
VERSION_PARAM = "v"
STYLESHEET_INDEX = "css/style.css"
_IMPORT_RE = re.compile(r"""@import\s+url\(\s*['"]?([^'")?]+)""")

# 版付きの URL（?v=）に付ける。版が変われば URL も変わるので、同じ URL の中身は変わらない
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


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
    return hashlib.sha256(path.read_bytes()).hexdigest()[:VERSION_LENGTH]


@cache
def static_url(rel: str) -> str:
    """static/ からの相対パス（先頭の /static/ は付けても付けなくてもよい）を、版付きの URL にする。
    ファイルが無いときは版を付けずに返し、ログに残す（ページは描けるようにする）。
    結果は覚えておき、2 回目からはファイルを見に行かない（再起動まで同じ URL を返す）"""
    rel = rel.removeprefix("/static/").lstrip("/")
    path = _resolve(rel)
    try:
        if path is not None:
            return f"/static/{rel}?{VERSION_PARAM}={_version(path)}"
    except OSError:  # 調べている間に消えた・読めない
        pass
    logger.warning("static_url: ファイルが見つからないので版を付けない: %s", rel)
    return f"/static/{rel}"


@cache
def stylesheet_urls() -> tuple[str, ...]:
    """style.css の @import の順に、読み込む CSS の版付き URL を返す（覚えておき、再起動まで同じものを返す）"""
    index = _resolve(STYLESHEET_INDEX)
    if index is None:
        logger.warning("stylesheet_urls: %s が見つからない", STYLESHEET_INDEX)
        return ()
    base = Path(STYLESHEET_INDEX).parent
    return tuple(static_url((base / href).as_posix()) for href in _IMPORT_RE.findall(index.read_text(encoding="utf-8")))


class VersionedStaticFiles(StaticFiles):
    """/static の配信。版付きの URL（?v=）で返したファイルだけ、ブラウザに長く覚えさせる（Q-35）。
    版の付かない URL（vendor・logo・コードの配色テーマなど）は、中身が変わっても URL が同じなので付けない"""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304) and _has_version(scope):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        return response


def _has_version(scope: Scope) -> bool:
    """URL に空でない ?v= が付いているか（parse_qs は空の値を落とす）"""
    return VERSION_PARAM in parse_qs(scope.get("query_string", b"").decode("latin-1"))
