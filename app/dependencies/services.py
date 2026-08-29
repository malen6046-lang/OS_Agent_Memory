"""Configuration-driven dependency assembly and provider lifecycle."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from typing import Any

from app.core.config import AppConfig
from app.orchestrator import MemoryOrchestrator
from app.orchestrator.ports import (
    AuditRepository,
    EvaluationService,
    ForgetService,
    IdempotencyRepository,
    KnowledgeService,
    MemoryRepository,
    PreferenceService,
    Retriever,
)
from contracts.schemas.provider import VectorStoreConfig

from .errors import ServiceLifecycleError, ServiceStartupError
from .mock_services import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    MockEmbeddingProvider,
    MockEvaluationService,
    MockForgetService,
    MockIdempotencyRepository,
    MockKnowledgeService,
    MockMemoryRepository,
    MockPreferenceService,
    MockRetriever,
    MockSafetyService,
    MockAuditRepository,
    MockVectorStoreAdapter,
)


@dataclass
class ServiceContainer:
    """Application-scoped service registry with ordered provider lifecycle."""

    preference_service: PreferenceService
    knowledge_service: KnowledgeService
    retriever: Retriever
    forget_service: ForgetService
    safety_service: Any = None
    embedding_provider: Any = None
    vector_store: Any = None
    vector_store_config: VectorStoreConfig | None = None
    memory_repository: MemoryRepository | None = None
    idempotency_repository: IdempotencyRepository | None = None
    audit_repository: AuditRepository | None = None
    evaluation_service: EvaluationService | None = None
    fallback_retriever: Retriever | None = None
    mode: str = "mock"
    dependency_timeouts: dict[str, float] = field(
        default_factory=lambda: {"default": 0.5}
    )
    _started_providers: list[Any] = field(default_factory=list, init=False)

    @property
    def hybrid_retriever(self) -> Retriever:
        return self.retriever

    @property
    def vector_store_adapter(self) -> Any:
        return self.vector_store

    async def start(self) -> None:
        """Start providers once, in dependency order."""
        if self._started_providers:
            return
        if self.embedding_provider is None or self.vector_store is None:
            raise ServiceStartupError(
                "EmbeddingProvider and VectorStoreAdapter are required "
                "for application lifecycle startup"
            )

        try:
            await _invoke(self.embedding_provider.start)
            self._started_providers.append(self.embedding_provider)
            await _invoke(self.vector_store.start, self.vector_store_config)
            self._started_providers.append(self.vector_store)
        except Exception as exc:
            await self._rollback_started()
            if isinstance(exc, ServiceStartupError):
                raise
            raise ServiceStartupError(
                f"provider startup failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def close(self) -> None:
        """Close only providers that started, in reverse order."""
        errors: list[str] = []
        while self._started_providers:
            provider = self._started_providers.pop()
            try:
                await _invoke(provider.close)
            except Exception as exc:
                errors.append(f"{type(provider).__name__}: {exc}")
        if errors:
            raise ServiceLifecycleError(
                "provider shutdown failed: " + "; ".join(errors)
            )

    async def warmup(self) -> None:
        """Load the embedding model before the first user request.

        Providers are already started at this point.  A single minimal encode
        keeps cold-start latency out of the first real ingest/search request;
        it does not write anything to the vector store.
        """
        if self.embedding_provider is None:
            raise ServiceStartupError("EmbeddingProvider is required for warmup")
        await _invoke(self.embedding_provider.health)
        await _invoke(
            self.embedding_provider.encode,
            ["os-agent-memory-startup-warmup"],
        )

    async def _rollback_started(self) -> None:
        while self._started_providers:
            provider = self._started_providers.pop()
            try:
                await _invoke(provider.close)
            except Exception:
                pass


def build_service_container(config: AppConfig) -> ServiceContainer:
    """Build one service instance per application from validated config."""
    mode = config.services.mode
    embedding_provider = _build_embedding_provider(config)
    vector_store = _build_vector_store(config)

    if mode == "mock":
        memory_repository = _load_optional(
            "MemoryRepository",
            config.services.memory_repository_implementation,
            MockMemoryRepository,
            config=config,
        )
        idempotency_repository = _load_optional(
            "IdempotencyRepository",
            config.services.idempotency_repository_implementation,
            MockIdempotencyRepository,
            config=config,
        )
        audit_repository = _load_optional(
            "AuditRepository",
            config.services.audit_repository_implementation,
            MockAuditRepository,
            config=config,
        )
        evaluation_service = MockEvaluationService()
        preference_service = _load_optional(
            "PreferenceService",
            config.services.preference_implementation,
            MockPreferenceService,
            config=config,
            app_config=config,
        )
        safety_service = _load_optional(
            "SafetyService",
            config.services.safety_implementation,
            MockSafetyService,
            config=config,
            app_config=config,
        )
        knowledge_service = _load_optional(
            "KnowledgeService",
            config.services.knowledge_implementation,
            MockKnowledgeService,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            memory_repository=memory_repository,
            config=config.retrieval,
            app_config=config,
        )
        if config.services.retriever_implementation:
            retriever = _load_required(
                "HybridRetriever",
                config.services.retriever_implementation,
                knowledge_service=knowledge_service,
                embedding_provider=embedding_provider,
                vector_store=vector_store,
                memory_repository=memory_repository,
                config=config.retrieval,
                app_config=config,
            )
        else:
            retriever = MockRetriever(
                embedding_provider=embedding_provider,
                vector_store=vector_store,
                memory_repository=memory_repository,
            )
        fallback_retriever = None
        forget_service = _load_optional(
            "ForgetService",
            config.services.forget_implementation,
            MockForgetService,
            retriever=retriever,
            config=config,
            app_config=config,
        )
    else:
        memory_repository = _load_required(
            "MemoryRepository",
            config.services.memory_repository_implementation,
            config=config,
        )
        idempotency_repository = _load_required(
            "IdempotencyRepository",
            config.services.idempotency_repository_implementation,
            config=config,
        )
        audit_repository = _load_required(
            "AuditRepository",
            config.services.audit_repository_implementation,
            config=config,
        )
        evaluation_service = _load_required(
            "EvaluationService",
            config.services.evaluation_implementation,
            config=config,
        )
        preference_service = _load_required(
            "PreferenceService",
            config.services.preference_implementation,
            config=config,
            app_config=config,
        )
        safety_service = _load_required(
            "SafetyService",
            config.services.safety_implementation,
            config=config,
            app_config=config,
        )
        knowledge_service = _load_required(
            "KnowledgeService",
            config.services.knowledge_implementation,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            memory_repository=memory_repository,
            config=config.retrieval,
            app_config=config,
        )
        retriever = _load_required(
            "HybridRetriever",
            config.services.retriever_implementation,
            knowledge_service=knowledge_service,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            memory_repository=memory_repository,
            config=config.retrieval,
            app_config=config,
        )
        fallback_retriever = None
        if config.services.fallback_retriever_implementation:
            fallback_retriever = _load_required(
                "Fallback HybridRetriever",
                config.services.fallback_retriever_implementation,
                knowledge_service=knowledge_service,
                embedding_provider=embedding_provider,
                vector_store=vector_store,
                memory_repository=memory_repository,
                config=config.retrieval,
                app_config=config,
            )
        forget_service = _load_required(
            "ForgetService",
            config.services.forget_implementation,
            retriever=retriever,
            config=config,
            app_config=config,
        )

    vector_provider = config.vector_store.provider.strip().lower()
    contract_vector_provider = {
        "mock": "memory",
        "memory": "memory",
        "fallback": "faiss",
        "faiss": "faiss",
        "kylin": "kylin",
    }[vector_provider]
    vector_store_config = VectorStoreConfig(
        provider=contract_vector_provider,
        collection_name=config.vector_store.collection_name,
        expected_dimension=config.vector_store.expected_dimension,
        metric=config.vector_store.metric,
    )

    return ServiceContainer(
        preference_service=preference_service,
        safety_service=safety_service,
        forget_service=forget_service,
        knowledge_service=knowledge_service,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        retriever=retriever,
        vector_store_config=vector_store_config,
        memory_repository=memory_repository,
        idempotency_repository=idempotency_repository,
        audit_repository=audit_repository,
        evaluation_service=evaluation_service,
        fallback_retriever=fallback_retriever,
        mode=mode,
        dependency_timeouts=dict(config.services.dependency_timeouts),
    )


def build_mock_container() -> ServiceContainer:
    """Compatibility factory used by existing orchestrator unit tests."""
    from app.core.config import (
        ApplicationConfig,
        EmbeddingConfig,
        LoggingConfig,
        RetrievalConfig,
        StorageConfig,
    )

    config = AppConfig(
        app=ApplicationConfig(name="os-agent-memory", version="1.0.0"),
        storage=StorageConfig(data_dir=".", sqlite_file="memory.db"),
        embedding=EmbeddingConfig(provider="mock", model_name="default"),
        vector_store={"provider": "mock"},
        retrieval=RetrievalConfig(top_k_default=5, candidate_k=30),
        logging=LoggingConfig(level="INFO"),
    )
    return build_service_container(config)


def get_memory_orchestrator(
    container: ServiceContainer | None = None,
) -> MemoryOrchestrator:
    services = container or build_mock_container()
    return MemoryOrchestrator(
        preference_service=services.preference_service,
        knowledge_service=services.knowledge_service,
        retriever=services.retriever,
        forget_service=services.forget_service,
        safety_service=services.safety_service,
        idempotency_repository=services.idempotency_repository,
        repository=services.memory_repository,
        vector_store=services.vector_store,
        audit_repository=services.audit_repository,
        evaluation_service=services.evaluation_service,
        fallback_retriever=services.fallback_retriever,
        timeout_seconds=services.dependency_timeouts,
    )


def _build_embedding_provider(config: AppConfig) -> Any:
    provider = config.embedding.provider.strip().lower()
    if provider in {"mock", "deterministic_test"}:
        return MockEmbeddingProvider(config.embedding.model_name)
    if provider in {"fallback", "sentence_transformer"}:
        return FallbackEmbeddingProvider(config.embedding.model_name)
    if provider == "kylin":
        return _load_required(
            "Kylin EmbeddingProvider",
            config.embedding.implementation,
            model_name=config.embedding.model_name,
            config=config.embedding,
            app_config=config,
        )
    raise ServiceStartupError(
        f"unsupported embedding provider {config.embedding.provider!r}; "
        "expected mock, fallback, or kylin"
    )


def _build_vector_store(config: AppConfig) -> Any:
    provider = config.vector_store.provider.strip().lower()
    if provider in {"mock", "memory"}:
        return MockVectorStoreAdapter()
    if provider in {"fallback", "faiss"}:
        return FallbackVectorStoreAdapter()
    if provider == "kylin":
        return _load_required(
            "Kylin VectorStoreAdapter",
            config.vector_store.implementation,
            config=config.vector_store,
            app_config=config,
        )
    raise ServiceStartupError(
        f"unsupported vector provider {config.vector_store.provider!r}; "
        "expected mock, fallback, or kylin"
    )


def _load_required(
    component_name: str,
    implementation: str | None,
    **dependencies: Any,
) -> Any:
    if not implementation:
        raise ServiceStartupError(
            f"{component_name} real implementation is not configured"
        )

    module_name, separator, attribute_name = implementation.partition(":")
    if not separator:
        module_name, separator, attribute_name = implementation.rpartition(".")
    if not module_name or not attribute_name:
        raise ServiceStartupError(
            f"{component_name} implementation must use "
            "'package.module:factory' or 'package.module.Factory'"
        )

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute_name)
        return _instantiate(factory, dependencies)
    except ServiceStartupError:
        raise
    except Exception as exc:
        raise ServiceStartupError(
            f"cannot create {component_name} from {implementation!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _load_optional(
    component_name: str,
    implementation: str | None,
    default_factory: Any,
    **dependencies: Any,
) -> Any:
    if implementation is None:
        return default_factory()
    return _load_required(component_name, implementation, **dependencies)


def _instantiate(factory: Any, dependencies: dict[str, Any]) -> Any:
    if not callable(factory):
        raise TypeError("configured implementation is not callable")
    signature = inspect.signature(factory)
    accepted = {
        name: value
        for name, value in dependencies.items()
        if name in signature.parameters
    }
    return factory(**accepted)


async def _invoke(callable_: Any, *args: Any) -> Any:
    result = callable_(*args)
    if inspect.isawaitable(result):
        return await result
    return result
