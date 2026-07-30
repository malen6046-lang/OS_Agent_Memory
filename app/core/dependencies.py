from functools import lru_cache

from app.repositories.in_memory import InMemoryRepository
from app.services.platform import PlatformService


@lru_cache
def get_repository() -> InMemoryRepository:
    return InMemoryRepository()


@lru_cache
def get_platform_service() -> PlatformService:
    return PlatformService(repository=get_repository())
