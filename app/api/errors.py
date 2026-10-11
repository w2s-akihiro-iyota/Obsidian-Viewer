"""エラー画面（F-10）

ブラウザでページを開いたときだけ、FastAPI 既定の JSON（{"detail": ...}）の代わりに、
アプリの枠（base.html）の中にエラー画面を出す。URL とステータスは変えない（/error へ飛ばさない）。
JS が読む API・添付・HTMX の読み込みには、今まで通りの応答を返す。
"""
import html
import logging
from dataclasses import dataclass, replace

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import templates
from app.utils.helpers import is_admin_request
from app.utils.messages import get_error

logger = logging.getLogger("app.errors")

# ページではない場所。JS が読む API と、<img> などで読む添付には HTML を返さない
_NON_PAGE_PREFIXES = ("/api/", "/media/", "/static/")
_NOTE_PREFIX = "/view/"


@dataclass(frozen=True)
class ErrorPage:
    """エラー画面に出す内容。文言は messages.yaml の ID で持つ"""
    status: int
    title_id: str
    message_id: str
    show_search: bool = False   # 「ノートを検索」ボタンを出すか（探し直せば見つかりそうなときだけ）
    admin_hint_id: str = ""     # 管理者にだけ出すヒント
    for_note: bool = False      # ノートの URL か（管理者に、開こうとしたパスと新規作成・同期を出す）

    @property
    def title(self) -> str:
        return get_error(self.title_id)

    @property
    def message(self) -> str:
        return get_error(self.message_id)

    @property
    def admin_hint(self) -> str:
        return get_error(self.admin_hint_id) if self.admin_hint_id else ""


# アイコンは error.html がステータスと for_note から選ぶ
_NOTE_NOT_FOUND = ErrorPage(404, "E301", "E302", show_search=True, admin_hint_id="E313", for_note=True)
_PAGE_NOT_FOUND = ErrorPage(404, "E303", "E304", show_search=True)
_ADMIN_ONLY = ErrorPage(403, "E305", "E306")
_BAD_PATH = ErrorPage(400, "E307", "E308")
_SERVER_ERROR = ErrorPage(500, "E309", "E310", admin_hint_id="E314")
_OTHER_ERROR = ErrorPage(0, "E311", "E312")   # 上のどれでもないステータス（status は呼ぶ側で差し替える）


def error_page_for(status: int, path: str) -> ErrorPage:
    """ステータスと URL から、出すエラー画面を決める"""
    if status == 404:
        return _NOTE_NOT_FOUND if path.startswith(_NOTE_PREFIX) else _PAGE_NOT_FOUND
    if status == 403:
        return _ADMIN_ONLY
    if status == 400:
        return _BAD_PATH
    if status >= 500:
        return _SERVER_ERROR
    return replace(_OTHER_ERROR, status=status)


def wants_error_page(request: Request) -> bool:
    """エラー画面（HTML）を返す相手か。ブラウザでページを直接開いたときだけ"""
    if request.headers.get("hx-request"):
        return False
    if request.url.path.startswith(_NON_PAGE_PREFIXES):
        return False
    return "text/html" in request.headers.get("accept", "")


def _requested_note(request: Request) -> str:
    """管理者に見せる、開こうとしたノートのパス（/view/ を除いたもの）"""
    path = request.scope.get("path", "")
    return path[len(_NOTE_PREFIX):] if path.startswith(_NOTE_PREFIX) else path


def _fallback_html(page: ErrorPage) -> HTMLResponse:
    """エラー画面のテンプレートまで壊れているときの、素の HTML"""
    title = html.escape(page.title)
    message = html.escape(page.message)
    body = (f'<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>{title}</title></head>'
            f'<body><h1>{title}</h1><p>{message}</p><p><a href="/">ホームへ戻る</a></p></body></html>')
    return HTMLResponse(body, status_code=page.status)


def render_error_page(request: Request, page: ErrorPage, headers: dict | None = None) -> Response:
    """アプリの枠の中にエラー画面を描く。描けなければ素の HTML で返す"""
    is_admin = is_admin_request(request)
    try:
        return templates.TemplateResponse(request=request, name="error.html", status_code=page.status,
                                          headers=headers, context={
            "request": request,
            "is_localhost": is_admin,
            "page": page,
            "requested_note": _requested_note(request) if is_admin and page.for_note else "",
        })
    except Exception:
        logger.exception("Failed to render the error page")
        return _fallback_html(page)


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
    """HTTPException（ルートが無いときの 404 も含む）の応答"""
    if not wants_error_page(request):
        return await http_exception_handler(request, exc)
    return render_error_page(request, error_page_for(exc.status_code, request.url.path),
                             headers=getattr(exc, "headers", None))


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """想定外の例外（500）の応答。例外の中身は画面に出さない（ログには ServerErrorMiddleware が出す）"""
    if not wants_error_page(request):
        return PlainTextResponse("Internal Server Error", status_code=500)
    return render_error_page(request, _SERVER_ERROR)
