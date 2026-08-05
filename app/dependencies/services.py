"""Configuration-driven dependency assembly and provider lifecycle."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from typing import Any

from app.core.config import AppConfig, VectorStoreConfig
from app.orchestrator import MemoryOrchestrator
from app.orchestrator.ports import (
    ForgetService,
    KnowledgeService,
    PreferenceService,
    Retriever,
)
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

from .errors import ServiceLifecycleError, ServiceStartupError
from .mock_services import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    MockEmbeddingProvider,
    MockForgetService,
    MockKnowledgeService,
    MockPreferenceService,
    MockRetriever,
    MockSafetyService,
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
    mode: str = "mock"
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

    if mode == "mock":
        preference_service = MockPreferenceService()
        safety_service = MockSafetyService()
        forget_service = MockForgetService()
        knowledge_service = MockKnowledgeService()
        embedding_provider = _build_embedding_provider(config)
        vector_store = _build_vector_store(config)
        retriever = MockRetriever(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
    elif _has_explicit_service_implementations(config):
        preference_service = _load_required(
            "PreferenceService",
            config.services.preference_implementation,
            config=config,
        )
        safety_service = _load_required(
            "SafetyService",
            config.services.safety_implementation,
            config=config,
        )
        forget_service = _load_required(
            "ForgetService",
            config.services.forget_implementation,
            config=config,
        )
        knowledge_service = _load_required(
            "KnowledgeService",
            config.services.knowledge_implementation,
            config=config,
        )
        embedding_provider = _build_embedding_provider(config)
        vector_store = _build_vector_store(config)
        retriever = _load_required(
            "HybridRetriever",
            config.services.retriever_implementation,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            config=config.retrieval,
            app_config=config,
        )
    else:
        algorithm = build_knowledge_retrieval_services(config)
        embedding_provider = algorithm["embedding_provider"]
        vector_store = algorithm["vector_store"]
        knowledge_service = AsyncKnowledgeServiceAdapter(
            algorithm["knowledge_service"]
        )
        retriever = AsyncHybridRetrieverAdapter(algorithm["hybrid_retriever"])
        preference_service = AsyncPreferenceServiceAdapter(
            algorithm["preference_service"]
        )
        safety_service = AsyncSafetyServiceAdapter(algorithm["safety_service"])
        forget_service = AsyncForgetServiceAdapter(
            algorithm["forget_service"],
            retriever=algorithm["hybrid_retriever"],
            vector_store=vector_store,
            metadata_store=algorithm["knowledge_service"]._meta,
        )

    return ServiceContainer(
        preference_service=preference_service,
        safety_service=safety_service,
        forget_service=forget_service,
        knowledge_service=knowledge_service,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        retriever=retriever,
        vector_store_config=config.vector_store,
        mode=mode,
    )


def _has_explicit_service_implementations(config: AppConfig) -> bool:
    services = config.services
    return any(
        (
            services.preference_implementation,
            services.safety_implementation,
            services.forget_implementation,
            services.knowledge_implementation,
            services.retriever_implementation,
        )
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
        vector_store=VectorStoreConfig(provider="mock"),
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
