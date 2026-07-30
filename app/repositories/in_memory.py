from __future__ import annotations

from contracts.schemas import Envelope


class InMemoryRepository:
    """仅供骨架和契约测试使用；生产实现必须由独立 repository 替换。"""

    def __init__(self) -> None:
        self._events: dict[str, Envelope] = {}

    async def save_events(self, events: list[Envelope]) -> int:
        for event in events:
            self._events[f"{event.user_id}:{event.source_event_id}"] = event
        return len(events)
