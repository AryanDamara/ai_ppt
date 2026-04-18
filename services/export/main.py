from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

from core.logging import setup_logging, get_logger
from routers import export

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("export_service_starting")
    # Verify font directory exists on startup
    fonts_path = Path("/app/fonts")
    font_count = sum(1 for _ in fonts_path.rglob("*.ttf")) + \
                 sum(1 for _ in fonts_path.rglob("*.otf"))
    logger.info("fonts_available", count=font_count)
    yield
    logger.info("export_service_stopped")


app = FastAPI(
    title="PPTX Export Service",
    version="1.0.0",
    description="Converts AI presentation JSON to native PowerPoint files.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://api:8000"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(export.router, prefix="/api/v1", tags=["export"])


@app.get("/health")
async def health():
    """
    Deep health check.
    Verifies: server alive, S3 accessible, fonts present.
    Returns HTTP 200 if all green, HTTP 503 if any dependency is degraded.
    """
    from storage.s3_client import check_s3
    from fastapi.responses import JSONResponse

    s3_status  = await check_s3()
    font_count = sum(1 for _ in Path("/app/fonts").rglob("*.ttf")) + \
                 sum(1 for _ in Path("/app/fonts").rglob("*.otf"))
    all_ok     = s3_status == "ok" and font_count > 0

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status":          "healthy" if all_ok else "degraded",
            "s3":              s3_status,
            "fonts_available": font_count,
        },
    )
