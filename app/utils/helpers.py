from fastapi import Request, HTTPException

def is_request_local(request: Request):
    # Check if request is from localhost/127.0.0.1
    # Priority 1: Check HOST header (most reliable for localhost usage)
    host_header = request.headers.get("host", "").lower()
    if "localhost" in host_header or "127.0.0.1" in host_header or "[::1]" in host_header:
        return True

    # Priority 2: Check environment variable (manual override)
    import os
    if os.getenv("IS_LOCALHOST", "").lower() == "true":
        return True
        
    client_host = request.client.host
    # If behind proxy, check forwarded header
    forwarded_for = request.headers.get("X-Forwarded-For")
    
    if client_host == "127.0.0.1" or client_host == "localhost":
        return True
    
    # In some Docker environments, the host might be different, 
    # but we can check if it's the internal IP or if the user explicitly set a flag.
    return False

def check_localhost(request: Request):
    if not is_request_local(request):
        raise HTTPException(status_code=403, detail="Forbidden: Access allowed only from localhost")
