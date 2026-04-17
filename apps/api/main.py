from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import signal
import uuid

from core.config import get_settings
from core.logging import setup_logging, get_logger, request_id_var
from routers import generation, websocket
from services.db.session import init_db, check_postgres

settings = get_settings()
setup_logging()
logger = get_logger(__name__)

# Rate limiter — keyed by client IP address
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── Startup ──────────────────────────────────────────────────────────────
    logger.info("startup_initiated", environment=settings.environment)
    await init_db()
    logger.info("database_initialized")
    yield
    # ─── Shutdown ───────────────────────────────────────────────────────────
    logger.info("shutdown_initiated")
    # Signal Celery to stop accepting new jobs
    # Workers finishing current tasks will complete before dying
    try:
        from workers.celery_app import celery
        # Broadcast to all workers: stop accepting new tasks
        celery.control.cancel_consumer("celery", reply=True, timeout=5)
        # Wait for active tasks (with timeout to avoid hanging deploys)
        await asyncio.wait_for(_wait_for_celery_idle(), timeout=30)
    except Exception as e:
        logger.warning("shutdown_celery_drain_failed", error=str(e))
    logger.info("shutdown_complete")


async def _wait_for_celery_idle() -> None:
    """Poll until no Celery workers report active tasks."""
    from workers.celery_app import celery
    max_polls = 30
    for _ in range(max_polls):
        inspect = celery.control.inspect(timeout=2)
        active = inspect.active() or {}
        total_active = sum(len(tasks) for tasks in active.values())
        if total_active == 0:
            return
        await asyncio.sleep(1)


app = FastAPI(
    title="AI PPT Generator API",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiter error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def inject_request_id(request: Request, call_next):
    """Inject a unique request_id into every request for log correlation."""
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(req_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    request_id_var.reset(token)
    return response


@app.middleware("http")
async def validate_schema_version(request: Request, call_next):
    """
    Schema version negotiation.
    If client sends Accept-Schema-Version header and it doesn't match,
    return 406 Not Acceptable to prevent incompatible client/server pairs.
    """
    requested_version = request.headers.get("Accept-Schema-Version")
    if requested_version and requested_version != settings.schema_version:
        return JSONResponse(
            status_code=406,
            content={
                "error": "schema_version_mismatch",
                "server_version": settings.schema_version,
                "requested_version": requested_version,
                "message": f"Server supports schema {settings.schema_version}, "
                           f"client requested {requested_version}. Please update your client.",
            }
        )
    return await call_next(request)


app.include_router(generation.router, prefix="/api/v1", tags=["generation"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/health")
async def health():
    """
    Deep health check — verifies all critical dependencies.
    Returns 200 if all healthy, 503 if any dependency is degraded.
    Used by load balancer and monitoring.
    """
    from services.cache.semantic_cache import check_redis

    checks = {
        "api": "ok",
        "postgres": await check_postgres(),
        "redis": await check_redis(),
    }

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_ok else "degraded",
            "version": "1.0.0",
            "schema_version": settings.schema_version,
            "pipeline_version": settings.pipeline_version,
            "checks": checks,
        }
    )
