from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import ADMIN_PORT, ADMIN_ALLOWED_HOSTS
from app.utils.messages import get_error


def _host_name(host_header: str) -> str:
    """Host ヘッダからポートを除いたホスト名を取り出す（IPv6 の [::1]:8001 にも対応）"""
    host_header = host_header.strip().lower()
    if host_header.startswith("["):
        return host_header.split("]", 1)[0] + "]"
    return host_header.split(":", 1)[0]


def is_admin_request(request: Request) -> bool:
    """
    管理者としてのリクエストかを判定します。

    管理用ポート（ADMIN_PORT）に届いたリクエストだけを管理者とみなします。
    管理用ポートはホスト PC の 127.0.0.1 にだけ公開しているため、外部からは届きません。
    Host ヘッダは送り手が自由に書けるので、それだけで管理者にはしません。
    ただし管理用ポートでも Host が localhost 系でなければ拒否します（DNS リバインディング対策）。
    """
    server = request.scope.get("server")
    if not server or server[1] != ADMIN_PORT:
        return False

    return _host_name(request.headers.get("host", "")) in ADMIN_ALLOWED_HOSTS


def is_public_view(request: Request, view_as: str = "") -> bool:
    """
    外部の人に見せる範囲（公開ノートだけ）で作るかを判定します。

    外部の人と、管理者の「外部の人の表示」（?as=public）が対象です。
    外部の人が ?as=public を付けても変わりません。
    """
    return (not is_admin_request(request)) or view_as == "public"


def admin_guard(request: Request) -> JSONResponse | None:
    """
    管理者のリクエストでない場合、403 JSONResponseを返す。
    JSON APIエンドポイントでの使用を想定。
    使用例: if error := admin_guard(request): return error
    """
    if not is_admin_request(request):
        return JSONResponse(
            {"status": "error", "message": get_error("E101")},
            status_code=403
        )
    return None


def is_same_origin_request(request: Request) -> bool:
    """
    リクエストの送り元が、このアプリ自身のページかを判定します（CSRF対策）。

    ブラウザは別サイトからの POST に必ず Origin を付けるため、Origin（無ければ Referer）の
    ホスト部が Host ヘッダと一致するかで判定します。
    どちらも無いリクエストはブラウザ以外（curl 等）からのものなので通します。
    """
    source = request.headers.get("origin") or request.headers.get("referer")
    if source is None:
        return True
    if source == "null":
        return False
    return urlsplit(source).netloc.lower() == request.headers.get("host", "").lower()
