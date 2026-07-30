from typing import Protocol

from contracts.schemas import Envelope


class MemoryRepository(Protocol):
    async def save_events(self, events: list[Envelope]) -> int: ...
