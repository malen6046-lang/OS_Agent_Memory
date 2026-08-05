"""Async adapters for the synchronous preference, safety, and forget services."""

from __future__ import annotations

from typing import Any


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return value


class AsyncPreferenceServiceAdapter:
    """Expose preference extraction and resolution through async methods."""

    def __init__(self, service: Any) -> None:
        self._service = service

    async def extract(self, event: Any) -> Any:
        events = event if isinstance(event, list) else [event]
        candidates = self._service.extract([_plain(item) for item in events])
        return self._service.upsert(candidates)

    async def resolve(
        self,
        user_id: str,
        scene: str = "",
        keys: list[str] | None = None,
    ) -> Any:
        return self._service.resolve(user_id=user_id, scene=scene, keys=keys)


class AsyncSafetyServiceAdapter:
    """Expose sensitive-data checks through an async boundary."""

    def __init__(self, service: Any) -> None:
        self._service = service

    async def check(self, text: str) -> dict[str, Any]:
        return self._service.check(text)


class AsyncForgetServiceAdapter:
    """Expose two-phase natural-language forgetting through async methods."""

    def __init__(
        self,
        service: Any,
        *,
        retriever: Any,
        vector_store: Any,
        metadata_store: dict[str, Any],
    ) -> None:
        self._service = service
        self._retriever = retriever
        self._vector_store = vector_store
        self._metadata_store = metadata_store

    async def preview(
        self,
        instruction: Any,
        *,
        user_id: str = "",
    ) -> dict[str, Any]:
        data = _plain(instruction)
        if isinstance(data, dict):
            user_id = data.get("user_id", user_id)
            instruction_text = data["instruction"]
        else:
            instruction_text = str(data)
        return self._service.preview(
            instruction_text,
            retriever=self._retriever,
            user_id=user_id,
            metadata_store=self._metadata_store,
        )

    async def execute(
        self,
        token: Any,
        *,
        selected_ids: list[str] | None = None,
        user_id: str = "",
    ) -> dict[str, Any]:
        data = _plain(token)
        if isinstance(data, dict):
            confirmation_token = data["confirmation_token"]
            selected_ids = data.get("selected_ids", selected_ids)
            user_id = data.get("user_id", user_id)
        else:
            confirmation_token = str(data)
        return self._service.execute(
            confirmation_token,
            selected_ids=selected_ids,
            user_id=user_id,
            vector_store=self._vector_store,
            metadata_store=self._metadata_store,
        )
