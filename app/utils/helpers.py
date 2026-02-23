from fastapi import Request
from fastapi.responses import JSONResponse

from app.utils.messages import get_error


def is_request_local(request: Request) -> bool:
    """
    リクエストがローカルアドレスからのものか確認します。
    """
    # localhost/127.0.0.1 からのリクエストかチェック
    # 優先順位 1: HOST ヘッダー（localhost での利用に最も信頼性が高い）
    host_header = request.headers.get("host", "").lower()
    if "localhost" in host_header or "127.0.0.1" in host_header or "[::1]" in host_header:
        return True

    # プロキシ経由の場合、forwarded ヘッダーをチェック
    forwarded_for = request.headers.get("X-Forwarded-For")

    client_host = request.client.host

    if client_host == "127.0.0.1" or client_host == "localhost":
        return True

    # Docker環境下では、ホスト名が異なる場合があります。
    return False


def localhost_guard(request: Request) -> JSONResponse | None:
    """
    localhostからのアクセスでない場合、403 JSONResponseを返す。
    JSON APIエンドポイントでの使用を想定。
    使用例: if error := localhost_guard(request): return error
    """
    if not is_request_local(request):
        return JSONResponse(
            {"status": "error", "message": get_error("E101")},
            status_code=403
        )
    return None
