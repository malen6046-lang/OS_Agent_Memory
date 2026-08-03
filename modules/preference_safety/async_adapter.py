"""异步适配器 — 将模块 A（偏好/安全/遗忘）包装为 async 接口.

Usage (by platform lead):
    from modules.preference_safety.async_adapter import (
        AsyncPreferenceServiceAdapter, AsyncSafetyServiceAdapter, AsyncForgetServiceAdapter,
    )
"""
from __future__ import annotations

from typing import Any


class AsyncPreferenceServiceAdapter:
    def __init__(self, preference_service: Any):
        self._ps = preference_service

    async def extract(self, events: list[Any]) -> list[dict]:
        return self._ps.extract(events)

    async def upsert(self, candidates: list[dict]) -> list[dict]:
        return self._ps.upsert(candidates)

    async def resolve(self, user_id: str, scene: str = "",
                      keys: list[str] | None = None) -> list[dict]:
        return self._ps.resolve(user_id=user_id, scene=scene, keys=keys)

    async def history(self, user_id: str, preference_key: str) -> list[dict]:
        return self._ps.history(user_id=user_id, preference_key=preference_key)


class AsyncSafetyServiceAdapter:
    def __init__(self, safety_service: Any):
        self._ss = safety_service

    async def check(self, text: str) -> dict:
        return self._ss.check(text)

    async def check_batch(self, texts: list[str]) -> list[dict]:
        return self._ss.check_batch(texts)


class AsyncForgetServiceAdapter:
    def __init__(self, forget_service: Any):
        self._fs = forget_service

    async def preview(self, instruction: str, retriever: Any = None,
                      user_id: str = "", metadata_store: dict | None = None) -> dict:
        return self._fs.preview(instruction, retriever=retriever, user_id=user_id,
                                metadata_store=metadata_store)

    async def execute(self, confirmation_token: str, selected_ids: list[str] | None = None,
                      user_id: str = "", vector_store: Any = None,
                      metadata_store: dict | None = None) -> dict:
        return self._fs.execute(confirmation_token, selected_ids=selected_ids, user_id=user_id,
                                vector_store=vector_store, metadata_store=metadata_store)
