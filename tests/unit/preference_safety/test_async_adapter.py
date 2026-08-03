"""模块 A 异步适配器测试 — preference/safety/forget 可被平台 async 调用."""
import pytest
from modules.preference_safety.preference_service import PreferenceService
from modules.preference_safety.safety_service import SafetyService
from modules.preference_safety.forget_service import ForgetService
from modules.preference_safety.async_adapter import (
    AsyncPreferenceServiceAdapter,
    AsyncSafetyServiceAdapter,
    AsyncForgetServiceAdapter,
)
from modules.knowledge_retrieval.service_factory import build_knowledge_retrieval_services


class TestAsyncPreference:
    @pytest.mark.asyncio
    async def test_extract(self):
        adapter = AsyncPreferenceServiceAdapter(PreferenceService())
        events = [{"text": "\u6211\u559c\u6b22\u6df1\u8272\u4e3b\u9898", "user_id": "u1"}]
        result = await adapter.extract(events)
        assert any(c["preference_key"] == "theme" for c in result)

    @pytest.mark.asyncio
    async def test_upsert_resolve(self):
        adapter = AsyncPreferenceServiceAdapter(PreferenceService())
        await adapter.upsert([{"preference_key": "theme", "value": "dark", "category": "ui",
                               "confidence": 0.9, "source_event_id": "e1", "user_id": "u1"}])
        resolved = await adapter.resolve(user_id="u1", keys=["theme"])
        assert len(resolved) == 1 and resolved[0]["value"] == "dark"


class TestAsyncSafety:
    @pytest.mark.asyncio
    async def test_check(self):
        adapter = AsyncSafetyServiceAdapter(SafetyService())
        r = await adapter.check("\u7535\u8bdd13800000000")
        assert r["has_sensitive"] is True


class TestAsyncForget:
    @pytest.mark.asyncio
    async def test_preview_execute(self):
        adapter = AsyncForgetServiceAdapter(ForgetService())
        plan = await adapter.preview("\u5fd8\u8bb0\u5173\u4e8e\u4e3b\u9898\u7684\u504f\u597d", user_id="u1")
        assert "confirmation_token" in plan
        result = await adapter.execute(plan["confirmation_token"], user_id="u1")
        assert result["success"] is True


class TestFactoryModuleA:
    def test_factory_returns_module_a(self):
        cfg = {"embedding": {"provider": "mock", "dim": 16},
               "vector_store": {"provider": "memory"}}
        svc = build_knowledge_retrieval_services(cfg)
        assert "preference_service" in svc
        assert "safety_service" in svc
        assert "forget_service" in svc
        assert isinstance(svc["preference_service"].resolve(), list)
        assert svc["safety_service"].check("\u5b89\u5168\u6587\u672c")["has_sensitive"] is False
