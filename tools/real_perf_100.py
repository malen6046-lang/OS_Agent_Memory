#!/usr/bin/env python3
"""Run a reproducible REAL-mode write/search performance baseline."""

from __future__ import annotations

import json
import statistics
import time
import uuid
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:18001/api/v1"
OUTPUT = Path("/tmp/real-perf-100.json")
WRITES = 100
SEARCHES = 20


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * p))
    return round(ordered[index], 3)


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min_ms": round(min(values), 3) if values else 0.0,
        "mean_ms": round(statistics.mean(values), 3) if values else 0.0,
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": round(max(values), 3) if values else 0.0,
    }


def main() -> None:
    user_id = f"perf-user-{uuid.uuid4().hex[:8]}"
    write_client: list[float] = []
    write_backend: list[float] = []
    search_client: list[float] = []
    search_backend: list[float] = []
    failures: list[dict[str, object]] = []

    with httpx.Client(timeout=60.0) as client:
        health = client.get(f"{BASE_URL}/health")
        health.raise_for_status()
        health_body = health.json()
        if not health_body.get("success") or health_body.get("data", {}).get("mock"):
            raise RuntimeError("API is not running in REAL mode")

        print(f"[正常] real模式已确认，测试用户={user_id}")
        print(f"[开始] 顺序写入 {WRITES} 条记忆")
        for index in range(WRITES):
            marker = f"{user_id}-{index}"
            request_id = f"req-write-{marker}"
            payload = {
                "contract_version": "1.0",
                "request_id": request_id,
                "idempotency_key": f"idem-{marker}",
                "user_id": user_id,
                "session_id": "real-perf-session",
                "scene": "office_automation",
                "source": "manual_config",
                "source_event_id": f"event-{marker}",
                "occurred_at": "2026-08-17T10:00:00+08:00",
                "payload": {
                    "content": f"性能测试记忆 {index}，标记 {marker}",
                    "memory_kind": "semantic",
                    "subtype": "fact",
                    "confidence": 0.9,
                    "importance": 0.8,
                },
            }
            started = time.perf_counter()
            try:
                response = client.post(
                    f"{BASE_URL}/events/ingest",
                    json=payload,
                    headers={"X-Request-ID": request_id},
                )
                elapsed = (time.perf_counter() - started) * 1000
                body = response.json()
                if response.status_code >= 400 or not body.get("success"):
                    failures.append({"operation": "write", "index": index, "body": body})
                else:
                    write_client.append(elapsed)
                    write_backend.append(float(body.get("meta", {}).get("elapsed_ms", 0)))
            except Exception as exc:  # noqa: BLE001
                failures.append({"operation": "write", "index": index, "error": repr(exc)})
            if (index + 1) % 10 == 0:
                print(f"  已写入 {index + 1}/{WRITES}")

        print(f"[开始] 执行 {SEARCHES} 次搜索")
        for index in range(SEARCHES):
            request_id = f"req-search-{user_id}-{index}"
            payload = {"user_id": user_id, "query": "性能测试记忆", "top_k": 5}
            started = time.perf_counter()
            try:
                response = client.post(
                    f"{BASE_URL}/memory/search",
                    json=payload,
                    headers={"X-Request-ID": request_id},
                )
                elapsed = (time.perf_counter() - started) * 1000
                body = response.json()
                if response.status_code >= 400 or not body.get("success"):
                    failures.append({"operation": "search", "index": index, "body": body})
                else:
                    search_client.append(elapsed)
                    search_backend.append(float(body.get("meta", {}).get("elapsed_ms", 0)))
            except Exception as exc:  # noqa: BLE001
                failures.append({"operation": "search", "index": index, "error": repr(exc)})
            if (index + 1) % 5 == 0:
                print(f"  已搜索 {index + 1}/{SEARCHES}")

    report = {
        "mode": "real",
        "base_url": BASE_URL,
        "user_id": user_id,
        "planned_writes": WRITES,
        "successful_writes": len(write_client),
        "planned_searches": SEARCHES,
        "successful_searches": len(search_client),
        "client_write_latency": summary(write_client),
        "backend_write_latency": summary(write_backend),
        "client_search_latency": summary(search_client),
        "backend_search_latency": summary(search_backend),
        "failure_count": len(failures),
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"报告文件：{OUTPUT}")


if __name__ == "__main__":
    main()
