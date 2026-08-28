"""End-to-end gate for the opt-in Algorithm V1.1 adapter graph."""

import os
import warnings
from datetime import datetime, timezone

import pytest
from starlette.exceptions import StarletteDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=StarletteDeprecationWarning,
)

from fastapi.testclient import TestClient

from adapters.knowledge_retrieval.knowledge import KnowledgeServiceAdapter
from adapters.knowledge_retrieval.retrieval import HybridRetrieverAdapter
from adapters.preference_safety.forget import ForgetServiceAdapter
from adapters.preference_safety.preference import PreferenceServiceAdapter
from adapters.preference_safety.safety import SafetyServiceAdapter
from app.core.config import ConfigManager
from app.dependencies import build_service_container, get_memory_orchestrator
from app.main import app
from contracts.schemas.envelope import Envelope
from contracts.schemas.forget import ForgetExecuteRequest, ForgetPreviewRequest
from contracts.schemas.retrieval import SearchRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _event() -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id="req_algorithm_ingest",
        idempotency_key="idem_algorithm_ingest",
        user_id="usr_algorithm",
        session_id=None,
        scene="desktop",
        source="user_behavior",
        source_event_id="evt_algorithm_ingest",
        occurred_at=datetime.now(timezone.utc),
        payload={"text": "我喜欢深色主题，并使用 Python。"},
    )


@pytest.mark.anyio
async def test_algorithm_profile_ingest_search_and_forget_round_trip():
    container = build_service_container(
        ConfigManager().load("algorithm_modules")
    )
    assert isinstance(container.preference_service, PreferenceServiceAdapter)
    assert isinstance(container.safety_service, SafetyServiceAdapter)
    assert isinstance(container.forget_service, ForgetServiceAdapter)
    assert isinstance(container.knowledge_service, KnowledgeServiceAdapter)
    assert isinstance(container.retriever, HybridRetrieverAdapter)
    assert container.retriever.runtime is container.knowledge_service.runtime

    orchestrator = get_memory_orchestrator(container)
    await container.start()
    try:
        ingested = await orchestrator.ingest(_event())

        assert ingested["success"] is True
        preference_values = {
            (item["preference_key"], item["value"])
            for item in ingested["data"]["preference_result"]
        }
        assert ("theme", "dark") in preference_values
        assert ("language", "python") in preference_values
        record = ingested["data"]["repository_result"]["records"][0]
        memory_id = record["memory_id"]
        assert record["attributes"]["algorithm_source"].endswith("8c1e47d")

        searched = await orchestrator.search(
            SearchRequest(
                request_id="req_algorithm_search",
                user_id="usr_algorithm",
                query="深色主题",
                top_k=5,
            )
        )

        assert searched["success"] is True
        assert searched["data"]["total"] == 1
        assert searched["data"]["items"][0]["memory_id"] == memory_id

        previewed = await orchestrator.preview_forget(
            ForgetPreviewRequest(
                request_id="req_algorithm_forget_preview",
                user_id="usr_algorithm",
                instruction="忘记关于深色主题的记忆",
            )
        )
        plan = previewed["data"]
        assert [item["memory_id"] for item in plan["candidates"]] == [
            memory_id
        ]
        forgotten = await orchestrator.execute_forget(
            ForgetExecuteRequest(
                request_id="req_algorithm_forget_execute",
                user_id="usr_algorithm",
                plan_id=plan["plan_id"],
                confirmation_token=plan["confirmation_token"],
                selected_ids=[memory_id],
            )
        )

        assert forgotten["success"] is True
        assert (
            container.memory_repository.records[memory_id].status.value
            == "tombstoned"
        )

        searched_after_forget = await orchestrator.search(
            SearchRequest(
                request_id="req_algorithm_search_after_forget",
                user_id="usr_algorithm",
                query="深色主题",
                top_k=5,
            )
        )
        assert searched_after_forget["success"] is True
        assert searched_after_forget["data"]["items"] == []
    finally:
        await container.close()


def test_algorithm_profile_starts_through_the_existing_fastapi_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in tuple(os.environ):
        if name.startswith("OS_AGENT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OS_AGENT_ENV", "algorithm_modules")

    with TestClient(app, raise_server_exceptions=False) as client:
        paths = client.app.openapi()["paths"]
        assert {
            "/api/v1/health",
            "/api/v1/events/ingest",
            "/api/v1/memory/search",
            "/api/v1/forget/preview",
            "/api/v1/forget/execute",
            "/api/v1/evaluations/run",
        } <= set(paths)
        container = client.app.state.service_container
        assert isinstance(
            container.knowledge_service,
            KnowledgeServiceAdapter,
        )
        assert isinstance(container.retriever, HybridRetrieverAdapter)

        response = client.post(
            "/api/v1/events/ingest",
            json=_event().model_dump(mode="json"),
        )
        body = response.json()

        assert response.status_code == 200
        assert body["success"] is True
        assert body["data"]["result"]["knowledge_result"]["records"]
