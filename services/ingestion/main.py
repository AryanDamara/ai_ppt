"""FastAPI application for document ingestion and retrieval."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.logging import setup_logging, get_logger
from routers import upload, search, documents
from pipeline.parsers.layout_parser import LayoutParser

setup_logging()
logger = get_logger("main")

# Pre-warm Docling and reranker at startup
_layout_parser = None
_reranker_warmed = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _layout_parser, _reranker_warmed
    logger.info("ingestion_service_starting")

    # Pre-warm Docling (downloads models if not cached ~60s first time)
    try:
        _layout_parser = LayoutParser()
        logger.info("Docling pipeline warmed")
    except Exception as e:
        logger.error(f"Docling warm-up failed: {e}")

    # Pre-warm reranker model
    try:
        from retrieval.reranker import _load_model
        _load_model()
        _reranker_warmed = True
    except Exception as e:
        logger.warning(f"Reranker warm-up failed (non-fatal): {e}")

    yield
    logger.info("ingestion_service_stopped")


app = FastAPI(
    title="Document Ingestion Service",
    version="1.0.0",
    description="RAG document ingestion and retrieval for AI presentation grounding",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://api:8000"],
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["*"],
)

app.include_router(upload.router,    prefix="/api/v1", tags=["ingestion"])
app.include_router(search.router,    prefix="/api/v1", tags=["retrieval"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])


@app.get("/health")
async def health():
    from core.config import get_settings
    s = get_settings()
    checks = {}

    # Pinecone
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=s.pinecone_api_key)
        pc.describe_index(s.pinecone_index_name)
        checks["pinecone"] = "ok"
    except Exception as e:
        checks["pinecone"] = f"error: {str(e)[:50]}"

    # Redis
    try:
        import redis
        r = redis.Redis.from_url(s.redis_url)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:50]}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", **checks}
