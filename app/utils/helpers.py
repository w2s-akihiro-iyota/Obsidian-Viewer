from fastapi import Request, HTTPException

def is_request_local(request: Request):
    """
    Check if the request is from localhost.
    """
    # Check if request is from localhost/127.0.0.1
    # Priority 1: Check HOST header (most reliable for localhost usage)
    host_header = request.headers.get("host", "").lower()
    if "localhost" in host_header or "127.0.0.1" in host_header or "[::1]" in host_header:
        return True

    # If behind proxy, check forwarded header
    forwarded_for = request.headers.get("X-Forwarded-For")
    
    client_host = request.client.host
    
    if client_host == "127.0.0.1" or client_host == "localhost":
        return True
    
    # In some Docker environments, the host might be different.
    return False

def check_localhost(request: Request):
    """
    Raise 403 if request is not local.
    """
    if not is_request_local(request):
        raise HTTPException(status_code=403, detail="Forbidden: Access allowed only from localhost")

def get_client_ip(request: Request):
    """
    Get client IP from request (considering proxy).
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host
