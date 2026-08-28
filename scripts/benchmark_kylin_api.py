"""Sequential end-to-end benchmark for a running Kylin-backed HTTP API."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080/api/v1")
    parser.add_argument("--ingest-iterations", type=int, default=5)
    parser.add_argument("--search-iterations", type=int, default=30)
    parser.add_argument("--warmup-iterations", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.ingest_iterations < 1:
        parser.error("--ingest-iterations must be positive")
    if args.search_iterations < 5:
        parser.error("--search-iterations must be at least 5")
    if args.warmup_iterations < 0:
        parser.error("--warmup-iterations cannot be negative")
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")

    base_url = args.base_url.rstrip("/")
    run_id = uuid4().hex
    user_id = f"usr_api_benchmark_{run_id}"
    query = "Python 深色主题 文档处理"
    memory_ids: list[str] = []
    ingest_ms: list[float] = []
    ingest_bytes: list[float] = []
    search_ms: list[float] = []
    search_bytes: list[float] = []
    started_at = time.perf_counter()

    health_ms, health, health_size = _request(
        "GET",
        f"{base_url}/health",
        None,
        args.timeout_seconds,
    )
    _require_success(health, "health")
    health_data = health.get("data", {})
    embedding = health_data.get("embedding", {})
    vector_store = health_data.get("vector_store", {})
    if embedding.get("provider") != "kylin":
        raise RuntimeError("HTTP service is not using the Kylin embedding provider")
    if vector_store.get("provider") != "kylin":
        raise RuntimeError("HTTP service is not using the Kylin vector provider")

    try:
        for index in range(args.ingest_iterations):
            payload = {
                "contract_version": "1.0",
                "request_id": f"req_api_benchmark_{run_id}_{index}",
                "idempotency_key": f"idem_api_benchmark_{run_id}_{index}",
                "user_id": user_id,
                "session_id": None,
                "scene": "sdk_api_benchmark",
                "source": "user_behavior",
                "source_event_id": f"evt_api_benchmark_{run_id}_{index}",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "content": (
                        f"麒麟 API 性能测试记忆 {index}："
                        "我使用 Python 处理文档，并偏好深色主题。"
                    ),
                    "benchmark_run": run_id,
                },
            }
            elapsed_ms, response, response_size = _request(
                "POST",
                f"{base_url}/events/ingest",
                payload,
                args.timeout_seconds,
            )
            _require_success(response, f"ingest[{index}]")
            records = (
                response.get("data", {})
                .get("result", {})
                .get("repository_result", {})
                .get("records", [])
            )
            if len(records) != 1 or not records[0].get("memory_id"):
                raise RuntimeError(f"ingest[{index}] returned invalid records")
            memory_ids.append(str(records[0]["memory_id"]))
            ingest_ms.append(elapsed_ms)
            ingest_bytes.append(float(response_size))

        search_payload = {
            "user_id": user_id,
            "query": query,
            "top_k": args.top_k,
            "filters": {},
        }
        for _ in range(args.warmup_iterations):
            _, response, _ = _request(
                "POST",
                f"{base_url}/memory/search",
                search_payload,
                args.timeout_seconds,
            )
            _require_search_hits(response, memory_ids)

        for index in range(args.search_iterations):
            elapsed_ms, response, response_size = _request(
                "POST",
                f"{base_url}/memory/search",
                search_payload,
                args.timeout_seconds,
            )
            _require_search_hits(response, memory_ids, index=index)
            search_ms.append(elapsed_ms)
            search_bytes.append(float(response_size))

        preview_ms, preview, preview_size = _request(
            "POST",
            f"{base_url}/forget/preview",
            {
                "user_id": user_id,
                "memory_ids": memory_ids,
                "reason": "Kylin API benchmark cleanup",
            },
            args.timeout_seconds,
        )
        _require_success(preview, "forget.preview")
        preview_data = preview.get("data", {})
        plan_id = preview_data.get("plan_id")
        token = preview_data.get("confirmation_token")
        if not plan_id or not token:
            raise RuntimeError("forget.preview did not return confirmation data")

        execute_ms, executed, execute_size = _request(
            "POST",
            f"{base_url}/forget/execute",
            {
                "user_id": user_id,
                "plan_id": plan_id,
                "confirmation_token": token,
                "selected_ids": memory_ids,
            },
            args.timeout_seconds,
        )
        _require_success(executed, "forget.execute")
        memory_ids.clear()

        cleanup_search_ms, cleanup, cleanup_size = _request(
            "POST",
            f"{base_url}/memory/search",
            search_payload,
            args.timeout_seconds,
        )
        _require_success(cleanup, "cleanup.search")
        cleanup_items = cleanup.get("data", {}).get("items", [])
        if cleanup_items:
            raise RuntimeError("benchmark cleanup records are still searchable")

        report = {
            "status": "ok",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "provider": {
                "embedding": embedding,
                "vector_store": vector_store,
            },
            "iterations": {
                "ingest": args.ingest_iterations,
                "search": args.search_iterations,
                "search_warmup": args.warmup_iterations,
                "top_k": args.top_k,
            },
            "latency_ms": {
                "health": round(health_ms, 3),
                "ingest": _summary(ingest_ms),
                "search": _summary(search_ms),
                "forget_preview": round(preview_ms, 3),
                "forget_execute": round(execute_ms, 3),
                "cleanup_search": round(cleanup_search_ms, 3),
            },
            "response_bytes": {
                "health": health_size,
                "ingest": _summary(ingest_bytes),
                "search": _summary(search_bytes),
                "forget_preview": preview_size,
                "forget_execute": execute_size,
                "cleanup_search": cleanup_size,
            },
            "total_elapsed_ms": round(
                (time.perf_counter() - started_at) * 1000,
                3,
            ),
            "cleanup": "passed",
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.output is not None:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            print(f"report written: {output}", file=sys.stderr)
        return 0
    finally:
        if memory_ids:
            print(
                "warning: benchmark records may require cleanup: "
                + ",".join(memory_ids),
                file=sys.stderr,
            )


def _request(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout_seconds: float,
) -> tuple[float, dict[str, Any], int]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{method} {url} returned invalid JSON") from exc
    if status >= 400:
        raise RuntimeError(f"{method} {url} failed with HTTP {status}: {parsed}")
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method} {url} returned non-object JSON")
    return elapsed_ms, parsed, len(raw)


def _require_success(response: dict[str, Any], operation: str) -> None:
    if response.get("success") is not True:
        raise RuntimeError(f"{operation} failed: {response.get('error')}")


def _require_search_hits(
    response: dict[str, Any],
    memory_ids: list[str],
    *,
    index: int | None = None,
) -> None:
    operation = "search" if index is None else f"search[{index}]"
    _require_success(response, operation)
    items = response.get("data", {}).get("items", [])
    returned = {str(item.get("memory_id")) for item in items}
    if not returned.intersection(memory_ids):
        raise RuntimeError(f"{operation} did not return a benchmark memory")


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("sample cannot be empty")
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 3),
        "mean": round(statistics.fmean(ordered), 3),
        "p50": round(_percentile(ordered, 0.50), 3),
        "p95": round(_percentile(ordered, 0.95), 3),
        "p99": round(_percentile(ordered, 0.99), 3),
        "max": round(ordered[-1], 3),
    }


def _percentile(ordered: list[float], quantile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


if __name__ == "__main__":
    raise SystemExit(main())
