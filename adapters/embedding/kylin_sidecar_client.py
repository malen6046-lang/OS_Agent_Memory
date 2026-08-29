"""Synchronous client for the local Kylin C++ Sidecar protocol."""

from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any


class KylinSidecarError(RuntimeError):
    """Base exception raised for Sidecar transport or protocol failures."""


class KylinSidecarTransportError(KylinSidecarError):
    """The local Unix socket could not be reached or timed out."""


class KylinSidecarProtocolError(KylinSidecarError):
    """The Sidecar returned malformed or mismatched protocol data."""


class KylinSidecarProviderError(KylinSidecarError):
    """The Sidecar reported a structured provider failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class KylinSidecarClient:
    """Send one newline-delimited JSON request per Unix-socket connection."""

    def __init__(
        self,
        socket_path: str | Path | None = None,
        timeout_seconds: float | None = None,
        max_response_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        uid = os.getuid() if hasattr(os, "getuid") else 0
        configured_path = os.getenv("OS_AGENT_KYLIN_SIDECAR_SOCKET")
        self.socket_path = Path(
            socket_path or configured_path or f"/tmp/os-agent-kylin-sidecar-{uid}.sock"
        )
        configured_timeout = os.getenv("OS_AGENT_KYLIN_SIDECAR_TIMEOUT_SECONDS")
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else configured_timeout or 30.0
        )
        if self.timeout_seconds <= 0:
            raise ValueError("Sidecar timeout must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self.max_response_bytes = max_response_bytes

    def health(self) -> dict[str, Any]:
        return self._call("health")

    def model_info(self) -> dict[str, Any]:
        return self._call("model_info")

    def encode(self, texts: list[str]) -> dict[str, Any]:
        return self._call("encode", texts=texts)

    def vector_start(self, config: dict[str, Any]) -> dict[str, Any]:
        return self._call("vector_start", config=config)

    def ensure_collection(self, spec: dict[str, Any]) -> dict[str, Any]:
        return self._call("ensure_collection", spec=spec)

    def vector_upsert(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._call("vector_upsert", items=items)

    def vector_query(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._call("vector_query", request=request)

    def vector_delete(self, vector_pks: list[int]) -> dict[str, Any]:
        return self._call("vector_delete", vector_pks=vector_pks)

    def vector_close(self) -> dict[str, Any]:
        return self._call("vector_close")

    def _call(self, action: str, **fields: Any) -> dict[str, Any]:
        request_id = f"req-py-{uuid.uuid4().hex}"
        payload = {"request_id": request_id, "action": action, **fields}
        wire = (
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        response = bytearray()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout_seconds)
                client.connect(str(self.socket_path))
                client.sendall(wire)
                while not response.endswith(b"\n"):
                    chunk = client.recv(65536)
                    if not chunk:
                        raise KylinSidecarProtocolError(
                            "Sidecar closed without a complete response"
                        )
                    response.extend(chunk)
                    if len(response) > self.max_response_bytes:
                        raise KylinSidecarProtocolError(
                            "Sidecar response exceeds configured size limit"
                        )
        except KylinSidecarError:
            raise
        except (OSError, TimeoutError) as exc:
            raise KylinSidecarTransportError(
                f"cannot call Kylin Sidecar at {self.socket_path}: {exc}"
            ) from exc

        try:
            decoded = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KylinSidecarProtocolError(
                "Sidecar response is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise KylinSidecarProtocolError("Sidecar response must be an object")
        if decoded.get("request_id") != request_id:
            raise KylinSidecarProtocolError("Sidecar request_id mismatch")
        if decoded.get("success") is True:
            data = decoded.get("data")
            if not isinstance(data, dict):
                raise KylinSidecarProtocolError(
                    "successful Sidecar response must contain object data"
                )
            return data
        error = decoded.get("error")
        if not isinstance(error, dict):
            raise KylinSidecarProtocolError(
                "failed Sidecar response must contain an error object"
            )
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            raise KylinSidecarProtocolError(
                "Sidecar error code and message must be strings"
            )
        raise KylinSidecarProviderError(code, message)
