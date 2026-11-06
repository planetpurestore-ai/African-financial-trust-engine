import os
import re
import uuid
import logging
import time
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("aft.request")

MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(12 * 1024 * 1024)))
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

async def request_size_guard(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds configured limit"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})

    supplied_request_id = request.headers.get("X-Request-ID")
    request_id = supplied_request_id if supplied_request_id and _REQUEST_ID.fullmatch(supplied_request_id) else uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    safe_path = request.url.path
    if safe_path.startswith("/v1/shared/trust-records/"):
        safe_path = "/v1/shared/trust-records/{token}"
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "http_path": safe_path,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise
    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "http_method": request.method,
            "http_path": safe_path,
            "http_status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
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
