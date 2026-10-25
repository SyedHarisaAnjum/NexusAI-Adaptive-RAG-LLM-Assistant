import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging_config import request_id_var, setup_logging
from app.routers import auth, chat, documents
from app.services.backup_service import create_backup

settings = get_settings()
setup_logging(settings.log_level, settings.log_json)
logger = logging.getLogger("app")
request_logger = logging.getLogger("app.request")

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")
UPLOAD_PATH = "/api/documents/upload"


async def _backup_loop(interval_hours: int) -> None:
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            await run_in_threadpool(create_backup)
        except Exception:
            logger.exception("backup_failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(auth.ensure_demo_user)
    backup_task = None
    if settings.environment == "production" and settings.backup_interval_hours > 0:
        backup_task = asyncio.create_task(_backup_loop(settings.backup_interval_hours))
    logger.info("startup", extra={"environment": settings.environment, "model": settings.gemini_model})
    yield
    if backup_task:
        backup_task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id, upload size guard, security headers and one structured log line per request."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        # Reject oversized uploads before the body is read (the multipart parser
        # would otherwise receive the whole file first).
        if request.method == "POST" and request.url.path == UPLOAD_PATH:
            length = request.headers.get("content-length")
            limit = (settings.max_upload_mb + 1) * 1024 * 1024  # +1 MB for multipart overhead
            if length is None:
                response = JSONResponse({"detail": "Content-Length header required."}, status_code=411)
            elif not length.isdigit() or int(length) > limit:
                response = JSONResponse(
                    {"detail": f"File exceeds {settings.max_upload_mb} MB limit."}, status_code=413
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        request_logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                # For streamed responses this is time to first byte.
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Log the details, but never send stack traces or internals to the client.
    logger.error("unhandled_error", exc_info=exc, extra={"path": request.url.path})
    return JSONResponse(
        {"detail": "Internal server error.", "request_id": request_id_var.get()},
        status_code=500,
    )


# Added last so it wraps everything, including the error responses above.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.get("/")
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "message": "API is healthy and running."}
