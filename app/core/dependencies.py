"""FastAPI dependency access to application-scoped services."""

from functools import lru_cache

from fastapi import Request

from app.repositories.in_memory import InMemoryRepository
from app.services.platform import MemoryApiService


@lru_cache
def get_repository() -> InMemoryRepository:
    return InMemoryRepository()


@lru_cache
def _fallback_api_service() -> MemoryApiService:
    """Used by isolated route tests that do not run the application lifespan."""

    return MemoryApiService(repository=get_repository())


def get_api_service(request: Request) -> MemoryApiService:
    return getattr(request.app.state, "api_service", None) or _fallback_api_service()
