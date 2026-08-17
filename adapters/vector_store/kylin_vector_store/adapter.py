"""ctypes adapter for the Kylin vector-engine C++ bridge."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Iterable

from contracts.schemas.provider import (
    CollectionSpec,
    DeleteResult,
    ProviderHealth,
    UpsertResult,
    VectorHit,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)


class KylinVectorStoreError(RuntimeError):
    """Raised when the Kylin vector bridge or SDK rejects an operation."""


class _VectorNative:
    def __init__(self, library: Any) -> None:
        self.library = library
        self._bind()

    def _bind(self) -> None:
        void_p = ctypes.c_void_p
        char_p = ctypes.c_char_p
        char_pp = ctypes.POINTER(char_p)
        int64_p = ctypes.POINTER(ctypes.c_int64)
        float_p = ctypes.POINTER(ctypes.c_float)
        char_p_p = ctypes.POINTER(char_p)
        self._signature(
            "osam_kve_open",
            [char_p, char_p, ctypes.c_int, char_p, ctypes.c_uint32, char_pp],
            void_p,
        )
        self._signature("osam_kve_close", [void_p], None)
        self._signature(
            "osam_kve_ensure_collection",
            [void_p, char_p, ctypes.c_int, char_p, char_pp],
            ctypes.c_int,
        )
        self._signature(
            "osam_kve_upsert",
            [
                void_p,
                char_p,
                ctypes.c_size_t,
                int64_p,
                char_p_p,
                char_p_p,
                char_p_p,
                char_p_p,
                float_p,
                ctypes.c_int,
                char_pp,
            ],
            ctypes.c_int,
        )
        self._signature(
            "osam_kve_query",
            [
                void_p,
                char_p,
                char_p,
                char_p,
                float_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                char_p,
                char_pp,
                char_pp,
            ],
            ctypes.c_int,
        )
        self._signature(
            "osam_kve_delete",
            [void_p, char_p, int64_p, ctypes.c_size_t, char_pp, char_pp],
            ctypes.c_int,
        )
        self._signature("osam_kve_free", [char_p], None)

    def _signature(self, name: str, argtypes: list[Any], restype: Any) -> None:
        function = getattr(self.library, name)
        try:
            function.argtypes = argtypes
            function.restype = restype
        except (AttributeError, TypeError):
            pass

    def open(
        self,
        app_id: str,
        db_file: str,
        encrypt: bool,
        key: str,
        timeout_ms: int,
    ) -> ctypes.c_void_p:
        error = ctypes.c_char_p()
        raw = self.library.osam_kve_open(
            _bytes(app_id),
            _bytes(db_file),
            int(encrypt),
            _bytes(key),
            int(timeout_ms),
            ctypes.byref(error),
        )
        if not raw:
            raise KylinVectorStoreError(self._take(error) or "open failed")
        return raw if isinstance(raw, ctypes.c_void_p) else ctypes.c_void_p(raw)

    def close(self, handle: ctypes.c_void_p) -> None:
        self.library.osam_kve_close(handle)

    def ensure_collection(
        self,
        handle: ctypes.c_void_p,
        name: str,
        dimension: int,
        metric: str,
    ) -> None:
        error = ctypes.c_char_p()
        code = self.library.osam_kve_ensure_collection(
            handle,
            _bytes(name),
            dimension,
            _bytes(metric),
            ctypes.byref(error),
        )
        self._check(code, error, "ensure_collection")

    def upsert(
        self,
        handle: ctypes.c_void_p,
        collection: str,
        items: list[VectorItem],
        dimension: int,
    ) -> int:
        count = len(items)
        pks = (ctypes.c_int64 * count)(*[item.vector_pk for item in items])
        memory_ids = _string_array(item.memory_id for item in items)
        user_ids = _string_array(item.user_id for item in items)
        statuses = _string_array(item.status.value for item in items)
        metadata = _string_array(
            json.dumps(item.metadata, ensure_ascii=False, separators=(",", ":"))
            for item in items
        )
        flat = (ctypes.c_float * (count * dimension))(
            *(value for item in items for value in item.vector)
        )
        error = ctypes.c_char_p()
        code = self.library.osam_kve_upsert(
            handle,
            _bytes(collection),
            count,
            pks,
            memory_ids,
            user_ids,
            statuses,
            metadata,
            flat,
            dimension,
            ctypes.byref(error),
        )
        self._check(code, error, "upsert")
        return count

    def query(
        self,
        handle: ctypes.c_void_p,
        collection: str,
        request: VectorQuery,
        metric: str,
    ) -> list[dict[str, Any]]:
        vector = (ctypes.c_float * len(request.vector))(*request.vector)
        output = ctypes.c_char_p()
        error = ctypes.c_char_p()
        candidate_top_k = 100 if request.filters else request.top_k
        code = self.library.osam_kve_query(
            handle,
            _bytes(collection),
            _bytes(request.user_id),
            _bytes(request.status.value),
            vector,
            len(request.vector),
            candidate_top_k,
            request.timeout_ms,
            _bytes(metric),
            ctypes.byref(output),
            ctypes.byref(error),
        )
        self._check(code, error, "query")
        payload = self._take(output) or "[]"
        parsed = json.loads(payload)
        if not isinstance(parsed, list):
            raise KylinVectorStoreError("query bridge returned non-list JSON")
        return parsed

    def delete(
        self,
        handle: ctypes.c_void_p,
        collection: str,
        vector_pks: list[int],
    ) -> list[int]:
        values = (ctypes.c_int64 * len(vector_pks))(*vector_pks)
        output = ctypes.c_char_p()
        error = ctypes.c_char_p()
        code = self.library.osam_kve_delete(
            handle,
            _bytes(collection),
            values,
            len(vector_pks),
            ctypes.byref(output),
            ctypes.byref(error),
        )
        self._check(code, error, "delete")
        parsed = json.loads(self._take(output) or "[]")
        return [int(value) for value in parsed]

    def _check(
        self, code: int, error: ctypes.c_char_p, operation: str
    ) -> None:
        message = self._take(error)
        if code:
            raise KylinVectorStoreError(
                f"{operation} failed (bridge code {code}): {message or 'unknown'}"
            )

    def _take(self, value: ctypes.c_char_p) -> str | None:
        if not value.value:
            return None
        result = value.value.decode("utf-8", errors="replace")
        self.library.osam_kve_free(value)
        value.value = None
        return result


class KylinVectorStoreAdapter:
    """Frozen ``VectorStoreAdapter`` backed by the Kylin vector engine."""

    provider_name = "kylin"

    def __init__(
        self,
        config: Any = None,
        app_config: Any = None,
        *,
        app_id: str | None = None,
        db_file: str | os.PathLike[str] | None = None,
        encrypt: bool | None = None,
        key: str | None = None,
        connect_timeout_ms: int = 5000,
        bridge_path: str | os.PathLike[str] | None = None,
        native: _VectorNative | None = None,
    ) -> None:
        self._configured = config
        data_dir = _value(getattr(app_config, "storage", None), "data_dir", "./data")
        default_db = Path(data_dir) / "vector.db"
        self._app_id = app_id or os.getenv("OS_AGENT_KYLIN_VECTOR_APP_ID", "os-agent-memory")
        self._db_file = Path(
            db_file or os.getenv("OS_AGENT_KYLIN_VECTOR_DB", str(default_db))
        ).expanduser()
        env_encrypt = os.getenv("OS_AGENT_KYLIN_VECTOR_ENCRYPT")
        self._encrypt = (
            encrypt
            if encrypt is not None
            else str(env_encrypt or "false").lower() in {"1", "true", "yes"}
        )
        self._key = key if key is not None else os.getenv("OS_AGENT_KYLIN_VECTOR_KEY", "")
        self._connect_timeout_ms = int(connect_timeout_ms)
        self._bridge_path = Path(bridge_path) if bridge_path else None
        self._native = native
        self._handle: ctypes.c_void_p | None = None
        self._config: VectorStoreConfig | None = None
        self._collection: CollectionSpec | None = None
        self._last_error: str | None = None
        self._sdk_version = os.getenv("OS_AGENT_KYLIN_SDK_VERSION") or "unknown"
        self._lock = threading.RLock()

    def start(self, config: VectorStoreConfig) -> ProviderHealth:
        validated = VectorStoreConfig.model_validate(config)
        with self._lock:
            if self._handle is not None:
                return self.health()
            if self._encrypt and not self._key:
                raise KylinVectorStoreError(
                    "encryption is enabled but OS_AGENT_KYLIN_VECTOR_KEY is empty"
                )
            self._db_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                if os.name == "posix":
                    self._db_file.parent.chmod(0o700)
                if self._native is None:
                    self._native = _VectorNative(
                        _load_vector_bridge(self._bridge_path)
                    )
                self._handle = self._native.open(
                    self._app_id,
                    str(self._db_file.resolve()),
                    self._encrypt,
                    self._key,
                    self._connect_timeout_ms,
                )
                self._config = validated
                self._sdk_version = _pkg_config_version(
                    "kysdk-vector-engine-client", self._sdk_version
                )
                self.ensure_collection(
                    CollectionSpec(
                        name=validated.collection_name,
                        dimension=validated.expected_dimension,
                        metric=validated.metric,
                    )
                )
                if os.name == "posix" and self._db_file.exists():
                    self._db_file.chmod(0o600)
                self._last_error = None
                return self.health()
            except Exception as exc:
                self._last_error = str(exc)
                self.close()
                raise

    def close(self) -> None:
        with self._lock:
            if self._handle is not None and self._native is not None:
                self._native.close(self._handle)
            self._handle = None
            self._collection = None

    def health(self, deep: bool = False) -> ProviderHealth:
        del deep
        status = "ok" if self._handle is not None else "stopped"
        details: dict[str, Any] = {
            "app_id": self._app_id,
            "db_file": str(self._db_file),
            "encrypt": self._encrypt,
            "sdk_version": self._sdk_version,
        }
        if self._collection is not None:
            details.update(
                collection_name=self._collection.name,
                dimension=self._collection.dimension,
                metric=self._collection.metric,
            )
        if self._last_error:
            details["last_error"] = self._last_error
        return ProviderHealth(
            provider=self.provider_name,
            status=status,
            details=details,
        )

    def ensure_collection(self, spec: CollectionSpec) -> None:
        validated = CollectionSpec.model_validate(spec)
        with self._lock:
            native, handle = self._require_started()
            if self._config and validated.dimension != self._config.expected_dimension:
                raise KylinVectorStoreError(
                    "collection dimension does not match VectorStoreConfig"
                )
            native.ensure_collection(
                handle,
                validated.name,
                validated.dimension,
                validated.metric,
            )
            self._collection = validated

    def upsert(self, items: list[VectorItem]) -> UpsertResult:
        validated = [VectorItem.model_validate(item) for item in items]
        if not validated:
            return UpsertResult(upserted=0)
        with self._lock:
            native, handle = self._require_started()
            collection = self._require_collection()
            for item in validated:
                if len(item.vector) != collection.dimension:
                    raise KylinVectorStoreError(
                        f"vector_pk {item.vector_pk} has dimension {len(item.vector)}; "
                        f"expected {collection.dimension}"
                    )
            count = native.upsert(
                handle, collection.name, validated, collection.dimension
            )
            return UpsertResult(upserted=count)

    def query(self, request: VectorQuery) -> list[VectorHit]:
        validated = VectorQuery.model_validate(request)
        with self._lock:
            native, handle = self._require_started()
            collection = self._require_collection()
            if len(validated.vector) != collection.dimension:
                raise KylinVectorStoreError(
                    f"query dimension {len(validated.vector)} does not match "
                    f"collection dimension {collection.dimension}"
                )
            raw_hits = native.query(
                handle,
                collection.name,
                validated,
                collection.metric,
            )
        hits: list[VectorHit] = []
        for raw in raw_hits:
            metadata = _json_mapping(raw.get("metadata", {}))
            if not _matches_filters(metadata, validated.filters):
                continue
            hits.append(
                VectorHit(
                    vector_pk=int(raw["vector_pk"]),
                    memory_id=str(raw["memory_id"]),
                    user_id=str(raw["user_id"]),
                    status=str(raw["status"]),
                    score=float(raw["score"]),
                )
            )
            if len(hits) >= validated.top_k:
                break
        return hits

    def delete(self, vector_pks: list[int]) -> DeleteResult:
        requested = list(dict.fromkeys(int(value) for value in vector_pks))
        if not requested:
            return DeleteResult(deleted=0, missing_vector_pks=[])
        with self._lock:
            native, handle = self._require_started()
            collection = self._require_collection()
            deleted_pks = native.delete(handle, collection.name, requested)
        deleted_set = set(deleted_pks)
        return DeleteResult(
            deleted=len(deleted_set),
            missing_vector_pks=[pk for pk in requested if pk not in deleted_set],
        )

    def _require_started(self) -> tuple[_VectorNative, ctypes.c_void_p]:
        if self._native is None or self._handle is None:
            raise RuntimeError("KylinVectorStoreAdapter is not started")
        return self._native, self._handle

    def _require_collection(self) -> CollectionSpec:
        if self._collection is None:
            raise RuntimeError("Kylin vector collection is not initialized")
        return self._collection


def _load_vector_bridge(explicit_path: Path | None) -> ctypes.CDLL:
    local = Path(__file__).with_name("native") / "build" / "libosam_kylin_vector_bridge.so"
    candidates = [
        str(explicit_path) if explicit_path else None,
        os.getenv("OS_AGENT_KYLIN_VECTOR_BRIDGE"),
        str(local),
        "libosam_kylin_vector_bridge.so",
    ]
    errors: list[str] = []
    for candidate in dict.fromkeys(value for value in candidates if value):
        try:
            return ctypes.CDLL(candidate)
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
    raise KylinVectorStoreError(
        "unable to load the Kylin vector bridge; run native/build.sh on the "
        "Kylin target or set OS_AGENT_KYLIN_VECTOR_BRIDGE. " + "; ".join(errors)
    )


def _string_array(values: Iterable[str]) -> Any:
    encoded = [_bytes(value) for value in values]
    return (ctypes.c_char_p * len(encoded))(*encoded)


def _bytes(value: str) -> bytes:
    return value.encode("utf-8")


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(metadata.get(key) == expected for key, expected in filters.items())


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


def _value(source: Any, name: str, default: Any) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)
