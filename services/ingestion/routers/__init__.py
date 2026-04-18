"""Routers package for ingestion service."""
from .upload import router
from .search import router
from .documents import router

__all__ = ["upload", "search", "documents"]