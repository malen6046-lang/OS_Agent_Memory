import asyncio

from app.dependencies import (
    MockForgetService,
    MockKnowledgeService,
    MockPreferenceService,
    MockRetriever,
    ServiceContainer,
    build_mock_container,
    get_memory_orchestrator,
)
from app.orchestrator import MemoryOrchestrator


def run(coroutine):
    return asyncio.run(coroutine)


def test_ingest_event_orchestrates_preference_then_knowledge():
    call_order = []
    preference_result = {"preferences": ["compact"]}
    knowledge_result = {"records": ["mem_1"]}

    class PreferenceSpy:
        async def extract(self, event):
            call_order.append(("preference.extract", event))
            return preference_result

    class KnowledgeSpy:
        async def ingest(self, event, extracted_preferences):
            call_order.append(
                ("knowledge.ingest", event, extracted_preferences)
            )
            return knowledge_result

    event = {"source_event_id": "evt_1"}
    orchestrator = MemoryOrchestrator(
        preference_service=PreferenceSpy(),
        knowledge_service=KnowledgeSpy(),
        retriever=MockRetriever(),
        forget_service=MockForgetService(),
    )

    result = run(orchestrator.ingest_event(event))

    assert call_order == [
        ("preference.extract", event),
        ("knowledge.ingest", event, preference_result),
    ]
    assert result == {
        "preference_result": preference_result,
        "knowledge_result": knowledge_result,
    }


def test_search_memory_delegates_to_injected_retriever():
    expected = {"items": ["mem_1"]}

    class RetrieverSpy:
        async def search(self, request):
            assert request == {"query": "format"}
            return expected

    orchestrator = MemoryOrchestrator(
        preference_service=MockPreferenceService(),
        knowledge_service=MockKnowledgeService(),
        retriever=RetrieverSpy(),
        forget_service=MockForgetService(),
    )

    assert run(orchestrator.search_memory({"query": "format"})) is expected


def test_preview_forget_delegates_to_injected_service():
    expected = {"plan_id": "forget_1"}

    class ForgetSpy:
        async def preview(self, request):
            assert request == {"memory_ids": ["mem_1"]}
            return expected

        async def execute(self, request):
            raise AssertionError("execute must not be called during preview")

    orchestrator = MemoryOrchestrator(
        preference_service=MockPreferenceService(),
        knowledge_service=MockKnowledgeService(),
        retriever=MockRetriever(),
        forget_service=ForgetSpy(),
    )

    result = run(orchestrator.preview_forget({"memory_ids": ["mem_1"]}))

    assert result is expected


def test_execute_forget_delegates_to_injected_service():
    expected = {"status": "executed"}

    class ForgetSpy:
        async def preview(self, request):
            raise AssertionError("preview must not be called during execute")

        async def execute(self, request):
            assert request == {"plan_id": "forget_1"}
            return expected

    orchestrator = MemoryOrchestrator(
        preference_service=MockPreferenceService(),
        knowledge_service=MockKnowledgeService(),
        retriever=MockRetriever(),
        forget_service=ForgetSpy(),
    )

    result = run(orchestrator.execute_forget({"plan_id": "forget_1"}))

    assert result is expected


def test_mock_container_provides_all_required_services():
    container = build_mock_container()

    assert isinstance(container.preference_service, MockPreferenceService)
    assert isinstance(container.knowledge_service, MockKnowledgeService)
    assert isinstance(container.retriever, MockRetriever)
    assert isinstance(container.forget_service, MockForgetService)
    assert isinstance(get_memory_orchestrator(container), MemoryOrchestrator)


def test_dependency_container_injects_exact_instances():
    preference = MockPreferenceService()
    knowledge = MockKnowledgeService()
    retriever = MockRetriever()
    forget = MockForgetService()
    container = ServiceContainer(preference, knowledge, retriever, forget)
    orchestrator = get_memory_orchestrator(container)

    event = {"source_event_id": "evt_1"}
    run(orchestrator.ingest_event(event))
    run(orchestrator.search_memory({"query": "test"}))
    run(orchestrator.preview_forget({"memory_ids": ["mem_1"]}))
    run(orchestrator.execute_forget({"plan_id": "forget_mock_plan"}))

    assert preference.calls == [("extract", event)]
    assert knowledge.calls[0][0] == "ingest"
    assert knowledge.calls[0][1] is event
    assert knowledge.calls[0][2] == {"preferences": [], "mock": True}
    assert retriever.calls == [("search", {"query": "test"})]
    assert forget.calls == [
        ("preview", {"memory_ids": ["mem_1"]}),
        ("execute", {"plan_id": "forget_mock_plan"}),
    ]
