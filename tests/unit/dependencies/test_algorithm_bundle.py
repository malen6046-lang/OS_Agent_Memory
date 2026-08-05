"""Integration contract for the one-factory, five-adapter algorithm bundle."""

import pytest

from app.core.config import ConfigManager
from modules.knowledge_retrieval.async_adapter import (
    AsyncHybridRetrieverAdapter,
    AsyncKnowledgeServiceAdapter,
)
from modules.knowledge_retrieval.service_factory import (
    build_knowledge_retrieval_services,
)
from modules.preference_safety.async_adapter import (
    AsyncForgetServiceAdapter,
    AsyncPreferenceServiceAdapter,
    AsyncSafetyServiceAdapter,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_one_factory_builds_services_for_all_five_async_adapters():
    algorithm = build_knowledge_retrieval_services(
        ConfigManager().load("development")
    )
    assert {
        "knowledge_service",
        "hybrid_retriever",
        "preference_service",
        "safety_service",
        "forget_service",
    } <= algorithm.keys()

    algorithm["embedding_provider"].start()
    algorithm["vector_store"].start({"dim": 768})

    knowledge = AsyncKnowledgeServiceAdapter(algorithm["knowledge_service"])
    retrieval = AsyncHybridRetrieverAdapter(algorithm["hybrid_retriever"])
    preference = AsyncPreferenceServiceAdapter(algorithm["preference_service"])
    safety = AsyncSafetyServiceAdapter(algorithm["safety_service"])
    forget = AsyncForgetServiceAdapter(
        algorithm["forget_service"],
        retriever=algorithm["hybrid_retriever"],
        vector_store=algorithm["vector_store"],
        metadata_store=algorithm["knowledge_service"]._meta,
    )

    await preference.extract(
        {"text": "我喜欢深色主题", "user_id": "usr_bundle", "scene": "desktop"}
    )
    assert await preference.resolve("usr_bundle")

    assert (await safety.check("手机号是13800138000"))["has_sensitive"] is True

    written = await knowledge.ingest(
        {
            "user_id": "usr_bundle",
            "scene": "office",
            "source_event_id": "evt_bundle",
            "payload": {
                "title": "bundle record",
                "body": "bundle integration content",
                "knowledge_type": "fact",
            },
        }
    )
    assert written["items"]
    assert (await retrieval.search(
        {"query": "bundle integration", "user_id": "usr_bundle", "top_k": 5}
    ))["items"]

    plan = await forget.preview("忘记 bundle integration", user_id="usr_bundle")
    executed = await forget.execute(
        plan["confirmation_token"], user_id="usr_bundle"
    )
    assert executed["success"] is True
