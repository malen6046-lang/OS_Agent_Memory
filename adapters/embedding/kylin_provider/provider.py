"""ctypes adapter for the Kylin CoreAI text-embedding C API.

The vendor session and result pointers stay inside this module.  Callers only
see the frozen Pydantic contracts from :mod:`contracts.schemas.provider`.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from contracts.schemas.provider import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderHealth,
)


class KylinEmbeddingError(RuntimeError):
    """Raised when the Kylin embedding SDK rejects an operation."""

    def __init__(self, operation: str, code: int, message: str) -> None:
        self.operation = operation
        self.code = int(code)
        self.sdk_message = message
        super().__init__(f"{operation} failed (SDK code {code}): {message}")


class _EmbeddingNative:
    """Typed, lifetime-safe wrapper around ``libkysdk-coreai-embedding``."""

    def __init__(self, library: Any) -> None:
        self.library = library
        self._bind()

    def _bind(self) -> None:
        void_p = ctypes.c_void_p
        int_p = ctypes.POINTER(ctypes.c_int)
        void_pp = ctypes.POINTER(void_p)
        self._signature("text_embedding_create_session", [], void_p)
        self._signature("text_embedding_destroy_session", [void_pp], None)
        self._signature("text_embedding_init_session", [void_p], ctypes.c_int)
        self._signature(
            "text_embedding_init_model",
            [void_p, ctypes.c_char_p],
            ctypes.c_int,
        )
        self._signature(
            "text_embedding_get_model_list",
            [void_p, int_p],
            void_p,
        )
        self._signature(
            "embedding_model_list_get_count",
            [void_p, int_p],
            ctypes.c_int,
        )
        self._signature(
            "embedding_model_list_get_model",
            [void_p, ctypes.c_int, int_p],
            void_p,
        )
        self._signature(
            "embedding_model_info_get_model_name",
            [void_p, int_p],
            ctypes.c_char_p,
        )
        self._signature(
            "embedding_model_info_get_model_dim",
            [void_p, int_p],
            ctypes.c_int,
        )
        self._signature(
            "text_embedding",
            [void_p, ctypes.c_char_p, void_pp],
            ctypes.c_bool,
        )
        self._signature(
            "embedding_result_get_error_code",
            [void_p],
            ctypes.c_int,
        )
        self._signature(
            "embedding_result_get_error_message",
            [void_p],
            ctypes.c_char_p,
        )
        self._signature(
            "embedding_result_get_vector_length",
            [void_p],
            ctypes.c_int,
        )
        self._signature(
            "embedding_result_get_vector_data",
            [void_p],
            ctypes.POINTER(ctypes.c_float),
        )
        self._signature("embedding_result_destroy", [void_pp], None)
        self._signature(
            "text_embedding_enable_internal_event_loop",
            [void_p, ctypes.c_bool],
            None,
        )

    def _signature(self, name: str, argtypes: list[Any], restype: Any) -> None:
        function = getattr(self.library, name)
        try:
            function.argtypes = argtypes
            function.restype = restype
        except (AttributeError, TypeError):
            # Python fakes used by unit tests do not expose ctypes attributes.
            pass

    def create_session(self) -> ctypes.c_void_p:
        raw = self.library.text_embedding_create_session()
        if isinstance(raw, ctypes.c_void_p):
            return raw
        return ctypes.c_void_p(raw)

    def destroy_session(self, session: ctypes.c_void_p) -> None:
        self.library.text_embedding_destroy_session(ctypes.byref(session))

    def init_session(self, session: ctypes.c_void_p) -> int:
        return int(self.library.text_embedding_init_session(session))

    def enable_internal_event_loop(
        self, session: ctypes.c_void_p, enabled: bool
    ) -> None:
        self.library.text_embedding_enable_internal_event_loop(session, enabled)

    def models(self, session: ctypes.c_void_p) -> list[tuple[str, int]]:
        error = ctypes.c_int(0)
        model_list = self.library.text_embedding_get_model_list(
            session, ctypes.byref(error)
        )
        if error.value or not model_list:
            raise KylinEmbeddingError(
                "text_embedding_get_model_list",
                error.value,
                "model list unavailable",
            )
        count = int(
            self.library.embedding_model_list_get_count(
                model_list, ctypes.byref(error)
            )
        )
        if error.value:
            raise KylinEmbeddingError(
                "embedding_model_list_get_count",
                error.value,
                "cannot read model count",
            )
        result: list[tuple[str, int]] = []
        for index in range(count):
            info = self.library.embedding_model_list_get_model(
                model_list, index, ctypes.byref(error)
            )
            if error.value or not info:
                raise KylinEmbeddingError(
                    "embedding_model_list_get_model",
                    error.value,
                    f"cannot read model index {index}",
                )
            raw_name = self.library.embedding_model_info_get_model_name(
                info, ctypes.byref(error)
            )
            dimension = int(
                self.library.embedding_model_info_get_model_dim(
                    info, ctypes.byref(error)
                )
            )
            if error.value or not raw_name or dimension <= 0:
                raise KylinEmbeddingError(
                    "embedding_model_info",
                    error.value,
                    f"invalid model metadata at index {index}",
                )
            result.append((_decode(raw_name), dimension))
        return result

    def init_model(self, session: ctypes.c_void_p, model_name: str) -> int:
        return int(
            self.library.text_embedding_init_model(
                session, model_name.encode("utf-8")
            )
        )

    def encode(self, session: ctypes.c_void_p, text: str) -> list[float]:
        result = ctypes.c_void_p()
        ok = bool(
            self.library.text_embedding(
                session,
                text.encode("utf-8"),
                ctypes.byref(result),
            )
        )
        if not ok or not result.value:
            raise KylinEmbeddingError(
                "text_embedding", 99, "SDK returned no result"
            )
        try:
            error_code = int(
                self.library.embedding_result_get_error_code(result)
            )
            if error_code:
                raw_message = self.library.embedding_result_get_error_message(
                    result
                )
                raise KylinEmbeddingError(
                    "text_embedding",
                    error_code,
                    _decode(raw_message) if raw_message else "unknown error",
                )
            length = int(
                self.library.embedding_result_get_vector_length(result)
            )
            data = self.library.embedding_result_get_vector_data(result)
            if length <= 0 or not data:
                raise KylinEmbeddingError(
                    "text_embedding", 99, "empty vector returned"
                )
            return [float(data[index]) for index in range(length)]
        finally:
            self.library.embedding_result_destroy(ctypes.byref(result))


class KylinEmbeddingProvider:
    """Frozen ``EmbeddingProvider`` implementation backed by Kylin CoreAI."""

    provider_name = "kylin"

    def __init__(
        self,
        model_name: str = "ensemble-embd_gte-base_uint8-text",
        config: Any = None,
        app_config: Any = None,
        *,
        expected_dimension: int | None = None,
        warmup: bool | None = None,
        library_path: str | os.PathLike[str] | None = None,
        native: _EmbeddingNative | None = None,
    ) -> None:
        del config
        self._model_name = model_name
        configured_dimension = _value(
            getattr(app_config, "vector_store", None),
            "expected_dimension",
            768,
        )
        self._expected_dimension = int(
            expected_dimension or configured_dimension
        )
        self._warmup = (
            _environment_flag("OS_AGENT_KYLIN_EMBEDDING_WARMUP", True)
            if warmup is None
            else bool(warmup)
        )
        self._library_path = Path(library_path) if library_path else None
        self._native = native
        self._session: ctypes.c_void_p | None = None
        self._dimension = 0
        self._started = False
        self._last_error: str | None = None
        self._last_latency_ms: float | None = None
        self._startup_latency_ms: float | None = None
        self._warmed_up = False
        self._lock = threading.RLock()
        self._sdk_version = os.getenv("OS_AGENT_KYLIN_SDK_VERSION") or "unknown"

    def start(self) -> ProviderHealth:
        with self._lock:
            if self._started:
                return self.health()
            started_at = time.perf_counter()
            try:
                if self._native is None:
                    self._native = _EmbeddingNative(
                        _load_embedding_library(self._library_path)
                    )
                session = self._native.create_session()
                if not session.value:
                    raise KylinEmbeddingError(
                        "text_embedding_create_session",
                        2,
                        "session allocation returned null",
                    )
                self._session = session
                code = self._native.init_session(session)
                if code:
                    raise KylinEmbeddingError(
                        "text_embedding_init_session", code, "session init failed"
                    )
                self._native.enable_internal_event_loop(session, False)
                available = dict(self._native.models(session))
                if self._model_name not in available:
                    raise KylinEmbeddingError(
                        "text_embedding_init_model",
                        1,
                        f"configured model {self._model_name!r} is unavailable; "
                        f"available={sorted(available)}",
                    )
                self._dimension = int(available[self._model_name])
                if self._dimension != self._expected_dimension:
                    raise KylinEmbeddingError(
                        "embedding_dimension_check",
                        2,
                        f"expected {self._expected_dimension}, got {self._dimension}",
                    )
                code = self._native.init_model(session, self._model_name)
                if code:
                    raise KylinEmbeddingError(
                        "text_embedding_init_model", code, "model init failed"
                    )
                if self._warmup:
                    self._encode_one("OS Agent memory embedding warmup")
                    self._warmed_up = True
                self._sdk_version = _pkg_config_version(
                    "kysdk-coreai-embedding", self._sdk_version
                )
                self._started = True
                self._last_error = None
                self._startup_latency_ms = (
                    time.perf_counter() - started_at
                ) * 1000
                return self.health()
            except Exception as exc:
                self._last_error = str(exc)
                self._destroy_session()
                raise

    def close(self) -> None:
        with self._lock:
            self._destroy_session()
            self._started = False

    def health(self, deep: bool = False) -> ProviderHealth:
        with self._lock:
            status = "ok" if self._started else "stopped"
            details: dict[str, Any] = {
                "model_name": self._model_name,
                "dimension": self._dimension,
                "expected_dimension": self._expected_dimension,
                "sdk_version": self._sdk_version,
                "warmed_up": self._warmed_up,
            }
            if self._last_error:
                details["last_error"] = self._last_error
            if self._last_latency_ms is not None:
                details["last_latency_ms"] = round(
                    self._last_latency_ms, 3
                )
            if self._startup_latency_ms is not None:
                details["startup_latency_ms"] = round(
                    self._startup_latency_ms, 3
                )
            if deep and self._started:
                started_at = time.perf_counter()
                try:
                    vector = self._encode_one("OS Agent memory health check")
                    details["deep_dimension"] = len(vector)
                    details["deep_latency_ms"] = round(
                        (time.perf_counter() - started_at) * 1000, 3
                    )
                except Exception as exc:
                    status = "degraded"
                    details["deep_error"] = str(exc)
            return ProviderHealth(
                provider=self.provider_name,
                status=status,
                details=details,
            )

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider=self.provider_name,
            model_name=self._model_name,
            dimension=self._dimension or self._expected_dimension,
            model_fingerprint=(
                f"{self._model_name}@{self._dimension or self._expected_dimension}d"
                f"+kysdk-{self._sdk_version}"
            ),
        )

    def encode(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            raise ValueError("texts must contain at least one item")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Kylin embedding input must be non-empty UTF-8 text")
        with self._lock:
            if not self._started or self._session is None:
                raise RuntimeError("KylinEmbeddingProvider is not started")
            vectors = [self._encode_one(text) for text in texts]
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self._model_name,
            dimension=self._dimension,
        )

    def _encode_one(self, text: str) -> list[float]:
        assert self._native is not None and self._session is not None
        started_at = time.perf_counter()
        vector = self._native.encode(self._session, text)
        self._last_latency_ms = (time.perf_counter() - started_at) * 1000
        if len(vector) != self._dimension:
            raise KylinEmbeddingError(
                "embedding_dimension_check",
                2,
                f"model reports {self._dimension}, result has {len(vector)}",
            )
        return vector

    def _destroy_session(self) -> None:
        if self._session is not None and self._native is not None:
            self._native.destroy_session(self._session)
        self._session = None
        self._dimension = 0
        self._warmed_up = False


def _load_embedding_library(
    explicit_path: Path | None,
) -> ctypes.CDLL:
    candidates: list[str] = []
    environment_path = os.getenv("OS_AGENT_KYLIN_EMBEDDING_LIBRARY")
    if explicit_path:
        candidates.append(str(explicit_path))
    if environment_path:
        candidates.append(environment_path)
    discovered = ctypes.util.find_library("kysdk-coreai-embedding")
    if discovered:
        candidates.append(discovered)
    candidates.extend(
        [
            "libkysdk-coreai-embedding.so.1",
            "libkysdk-coreai-embedding.so",
        ]
    )
    errors: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            return ctypes.CDLL(candidate)
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
    raise KylinEmbeddingError(
        "load_library",
        3,
        "unable to load libkysdk-coreai-embedding; " + "; ".join(errors),
    )


def _pkg_config_version(package: str, default: str) -> str:
    try:
        completed = subprocess.run(
            ["pkg-config", "--modversion", package],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return default
    return completed.stdout.strip() or default


def _environment_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _decode(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _value(source: Any, name: str, default: Any) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)
