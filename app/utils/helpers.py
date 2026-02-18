from fastapi import Request, HTTPException

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

def check_localhost(request: Request) -> None:
    """
    リクエストがローカルからでない場合、403 エラーをスローします。
    """
    if not is_request_local(request):
        raise HTTPException(status_code=403, detail="Forbidden: Access allowed only from localhost")

def get_client_ip(request: Request) -> str:
    """
    クライアントの IP アドレスを取得します（プロキシを考慮）。
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host
