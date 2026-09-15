import os
import secrets
import uuid
from fastapi import Request
from fastapi.responses import JSONResponse

MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(12 * 1024 * 1024)))

async def request_size_guard(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds configured limit"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})

    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/v1/") else "no-cache"
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

def allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]
