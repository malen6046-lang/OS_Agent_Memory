#!/usr/bin/env python3
"""REAL retrieval evaluation with automatic gold-to-actual ID mapping."""
from __future__ import annotations

import argparse, json, statistics, time, uuid
from pathlib import Path
import httpx


def find_key(value, key):
    if isinstance(value, dict):
        if key in value and isinstance(value[key], str):
            return value[key]
        for item in value.values():
            found = find_key(item, key)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_key(item, key)
            if found:
                return found
    return None


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return round(values[min(len(values) - 1, round((len(values) - 1) * p))], 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="real")
    parser.add_argument("--base-url", default="http://127.0.0.1:18001/api/v1")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.mode != "real":
        raise SystemExit("本评测脚本只允许 --mode real")

    root = Path(__file__).resolve().parents[1]
    corpus_path = root / "evaluation/dataset/knowledge_corpus.jsonl"
    query_path = root / "evaluation/dataset/retrieval_queries.jsonl"
    corpus = [json.loads(x) for x in corpus_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    queries = [json.loads(x) for x in query_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    user_id = f"retrieval-eval-{uuid.uuid4().hex[:8]}"
    id_map, latencies, failures, results = {}, [], [], []

    with httpx.Client(timeout=60.0) as client:
        health = client.get(f"{args.base_url}/health").json()
        if not health.get("success") or health.get("data", {}).get("mock"):
            raise SystemExit("API 不是 REAL 模式")
        print(f"[正常] REAL 模式，评测用户={user_id}")

        for index, item in enumerate(corpus):
            request_id = f"req-retrieval-ingest-{index}-{uuid.uuid4().hex[:8]}"
            payload = {
                "contract_version": "1.0", "request_id": request_id,
                "idempotency_key": f"idem-{request_id}", "user_id": user_id,
                "session_id": "retrieval-evaluation", "scene": item.get("scene_tags", ["galaxy_kylin_v11"])[0],
                "source": "manual_config", "source_event_id": item.get("source_refs", [item["memory_id"]])[0],
                "occurred_at": item.get("valid_from", "2026-07-01T09:00:00+08:00"),
                "payload": {"content": item.get("content_text", ""), "memory_kind": item.get("memory_kind", "semantic"),
                            "subtype": item.get("subtype", "fact"), "confidence": item.get("confidence", 0.9),
                            "importance": item.get("importance", 0.7)},
            }
            response = client.post(f"{args.base_url}/events/ingest", json=payload, headers={"X-Request-ID": request_id})
            body = response.json()
            actual = find_key(body, "memory_id")
            if response.status_code >= 400 or not body.get("success") or not actual:
                failures.append({"case_id": item["memory_id"], "stage": "ingest", "body": body})
            else:
                id_map[item["memory_id"]] = actual
            if (index + 1) % 10 == 0:
                print(f"  已写入 {index + 1}/{len(corpus)}")

        for index, case in enumerate(queries):
            topks = case.get("top_k", [1, 3, 5, 10])
            max_k = max(topks)
            request_id = f"req-retrieval-search-{index}-{uuid.uuid4().hex[:8]}"
            payload = {"user_id": user_id, "query": case["query"], "top_k": max_k}
            started = time.perf_counter()
            response = client.post(f"{args.base_url}/memory/search", json=payload, headers={"X-Request-ID": request_id})
            client_ms = (time.perf_counter() - started) * 1000
            body = response.json()
            items = body.get("data", {}).get("items", []) if isinstance(body, dict) else []
            returned = [x.get("memory_id") for x in items if isinstance(x, dict)]
            gold = case.get("expected", {}).get("gold_memory_ids", [])
            actual_gold = {id_map.get(x) for x in gold if id_map.get(x)}
            row = {"case_id": case["case_id"], "gold_memory_ids": gold, "actual_gold_ids": sorted(actual_gold),
                   "returned_memory_ids": returned, "client_ms": round(client_ms, 3),
                   "backend_ms": body.get("meta", {}).get("elapsed_ms", 0)}
            if not gold:
                row["status"] = "unlabeled"
                results.append(row)
                continue
            row["status"] = "labeled"
            for k in topks:
                row[f"hit_at_{k}"] = bool(actual_gold.intersection(returned[:k]))
            results.append(row); latencies.append(client_ms)
            if not actual_gold.intersection(returned[:max_k]):
                failures.append({"case_id": case["case_id"], "stage": "search", "category": "A", "detail": row})

    labeled = [x for x in results if x.get("status") == "labeled"]
    report = {"mode": "real", "user_id": user_id, "corpus_count": len(corpus), "query_count": len(queries),
              "labeled_query_count": len(labeled), "unlabeled_query_count": len(results) - len(labeled),
              "mapped_count": len(id_map), "failure_count": len(failures),
              "latency_p50_ms": percentile(latencies, .5), "latency_p95_ms": percentile(latencies, .95),
              "recall_at_1": round(sum(x.get("hit_at_1", False) for x in labeled) / len(labeled), 4) if labeled else 0,
              "recall_at_3": round(sum(x.get("hit_at_3", False) for x in labeled) / len(labeled), 4) if labeled else 0,
              "recall_at_5": round(sum(x.get("hit_at_5", False) for x in labeled) / len(labeled), 4) if labeled else 0,
              "recall_at_10": round(sum(x.get("hit_at_10", False) for x in labeled) / len(labeled), 4) if labeled else 0,
              "id_map": id_map, "failures": failures, "cases": results}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("corpus_count", "query_count", "mapped_count", "failure_count", "recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10", "latency_p50_ms", "latency_p95_ms")}, ensure_ascii=False, indent=2))
    print(f"报告文件：{output}")


if __name__ == "__main__":
    main()
