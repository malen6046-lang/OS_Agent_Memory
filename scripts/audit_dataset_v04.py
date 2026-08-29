# -*- coding: utf-8 -*-
"""Post-scale dataset audit for V0.4 ~500 samples."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

DS = Path(__file__).resolve().parents[1] / "evaluation" / "dataset"
VALID_SUB = {
    "output_style",
    "operation_habit",
    "security_policy",
    "workflow",
    "case",
    "template",
    "fact",
}
PREF_CAT = {"operation_habit", "output_style", "tool_choice", "safety_policy"}
REL = {"duplicate", "support", "extend", "replace", "contradict", "unrelated"}
STRAT = {"keep_old", "keep_new", "merge", "manual_review"}
ENTITY = {
    None,
    "password",
    "token",
    "id_card",
    "bank_card",
    "phone",
    "private_key",
    "address",
}


def load(name: str) -> list[dict]:
    return [
        json.loads(l)
        for l in (DS / name).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


def main() -> None:
    issues: list[tuple[str, str, str, str]] = []

    def add(sev: str, area: str, cid: str, msg: str) -> None:
        issues.append((sev, area, cid, msg))

    # ----- conflict -----
    for r in load("conflict.jsonl"):
        cid, split = r["case_id"], r.get("split")
        old, new, exp = r["old"], r["new"], r["expected"]
        rel, strat = exp.get("relation"), exp.get("strategy")
        if rel not in REL:
            add("error", "conflict", cid, f"bad relation {rel}")
        if strat not in STRAT:
            add("error", "conflict", cid, f"bad strategy {strat}")
        for side, mem in (("old", old), ("new", new)):
            if mem.get("subtype") not in VALID_SUB:
                add("error", "conflict", cid, f"{side}.subtype={mem.get('subtype')}")
            c = mem.get("content") or {}
            if "preference_key" not in c:
                add("error", "conflict", cid, f"{side} missing preference_key")
        ok = (old.get("content") or {}).get("preference_key")
        nk = (new.get("content") or {}).get("preference_key")
        ov = (old.get("content") or {}).get("value")
        nv = (new.get("content") or {}).get("value")
        if rel == "duplicate" and ov != nv:
            add("error", "conflict_gold", cid, f"duplicate values {ov!r}!={nv!r}")
        if rel in {"replace", "contradict"} and ok == nk and ov == nv:
            add("error", "conflict_gold", cid, f"{rel} but identical values")
        if rel == "support" and ov != nv:
            add("warn", "conflict_gold", cid, f"support values differ {ov!r}/{nv!r}")
        if rel == "extend" and ov == nv:
            add("warn", "conflict_gold", cid, "extend but values identical")
        if rel == "unrelated" and ok == nk:
            add("warn", "conflict_gold", cid, "unrelated but same preference_key")
        if strat == "keep_new":
            same = (
                old.get("valid_from") == new.get("valid_from")
                and old.get("confidence") == new.get("confidence")
                and old.get("revision") == new.get("revision")
            )
            if same:
                add("error", "conflict_gold", cid, "keep_new without stronger evidence")
        tags = " ".join(r.get("tags") or [])
        if rel and rel not in tags and split == "dev" and "v0.4" in tags:
            # soft: tags should mention relation
            pass
        rc = exp.get("reason_codes") or []
        if rel == "unrelated" and "different_entity" not in rc:
            add("warn", "conflict_meta", cid, f"unrelated reason_codes={rc}")

    # ----- forget -----
    for r in load("forget.jsonl"):
        cid, split = r["case_id"], r.get("split")
        dels = set((r.get("expected_preview") or {}).get("should_delete_ids") or [])
        keeps = set((r.get("expected_preview") or {}).get("should_keep_ids") or [])
        fids = {fx["memory_id"] for fx in r.get("memory_fixtures") or []}
        if dels & keeps:
            add("error", "forget", cid, f"delete∩keep={dels & keeps}")
        if (dels | keeps) != fids:
            add(
                "warn",
                "forget",
                cid,
                f"delete|keep != fixtures missing={fids - (dels | keeps)} extra={(dels | keeps) - fids}",
            )
        tok_p = (r.get("expected_preview") or {}).get("confirmation_token", "")
        tok_e = (r.get("expected_execute") or {}).get("confirmation_token", "")
        if split == "dev" and ("PLACEHOLDER" in str(tok_p) or "PLACEHOLDER" in str(tok_e)):
            add("error", "forget", cid, "PLACEHOLDER token")
        for fx in r.get("memory_fixtures") or []:
            t = fx.get("content_text") or ""
            if split == "dev":
                if "夹具记忆" in t or not t.strip():
                    add("error", "forget_sem", cid, f"placeholder {fx['memory_id']}: {t!r}")
                c = fx.get("content") or {}
                if list(c.keys()) == ["label"]:
                    add("error", "forget_sem", cid, f"label-only content {fx['memory_id']}")
                if any(k in t for k in ("应删除", "应保留", "should_delete", "should_keep")):
                    add("error", "forget_leak", cid, "answer leak")

    # ----- preference -----
    ep = re.compile(r"(这次|临时|仅本次|下次不用|只要这一次|仅限本次)")
    for r in load("preference.jsonl"):
        cid = r["case_id"]
        exp = r.get("expected") or {}
        prefs = exp.get("preferences") or []
        is_eph = bool(exp.get("is_ephemeral_instruction"))
        texts = []
        for ev in r.get("input_events") or []:
            texts.append(((ev.get("payload") or {}).get("text") or ""))
        ut = " ".join(texts)
        if is_eph and prefs:
            add("error", "pref", cid, "ephemeral but preferences non-empty")
        if (not is_eph) and ep.search(ut) and prefs:
            add("warn", "pref", cid, f"long-term gold but ephemeral wording: {ut[:40]}")
        for i, pref in enumerate(prefs):
            cat = pref.get("category")
            if cat not in PREF_CAT:
                add("error", "pref", cid, f"bad category {cat}")
            for f in (
                "preference_key",
                "value",
                "category",
                "scope",
                "scope_value",
                "polarity",
                "status",
            ):
                if f not in pref:
                    add("error", "pref", cid, f"missing {f} in preferences[{i}]")

    # ----- retrieval / corpus -----
    corpus = {c["memory_id"]: c for c in load("knowledge_corpus.jsonl")}
    for mid, c in corpus.items():
        if c.get("subtype") not in VALID_SUB:
            add("error", "corpus", mid, f"bad subtype {c.get('subtype')}")
        if not (c.get("content_text") or "").strip():
            add("error", "corpus", mid, "empty content_text")
    for r in load("retrieval_queries.jsonl"):
        cid = r["case_id"]
        golds = (r.get("expected") or {}).get("gold_memory_ids")
        if golds is None:
            add("error", "retrieval", cid, "missing gold_memory_ids")
            continue
        for gid in golds:
            if gid not in corpus:
                add("error", "retrieval", cid, f"gold missing {gid}")
            elif corpus[gid].get("status") not in (None, "active"):
                add("warn", "retrieval", cid, f"gold {gid} status={corpus[gid].get('status')}")

    # ----- security -----
    for r in load("security.jsonl"):
        cid = r["case_id"]
        exp = r.get("expected") or {}
        blocked = exp.get("blocked_or_masked")
        et = exp.get("entity_type")
        if et not in ENTITY:
            add("error", "security", cid, f"bad entity_type {et}")
        if blocked and et is None:
            add("warn", "security", cid, "blocked but entity_type null")
        if (not blocked) and et is not None:
            add("warn", "security", cid, f"not blocked but entity_type={et}")

    # ----- duplicates / id collisions -----
    for name, key in [
        ("preference.jsonl", "case_id"),
        ("retrieval_queries.jsonl", "case_id"),
        ("conflict.jsonl", "case_id"),
        ("forget.jsonl", "case_id"),
        ("security.jsonl", "case_id"),
        ("knowledge_corpus.jsonl", "memory_id"),
    ]:
        ids = [r[key] for r in load(name)]
        dup = [i for i, c in Counter(ids).items() if c > 1]
        if dup:
            add("error", "dup", name, f"duplicate ids: {dup[:5]} ... n={len(dup)}")

    # forget fixture id uniqueness within case already checked; across cases OK

    # ----- freeze split integrity: frozen cases still present -----
    man = json.loads((DS / "freeze_manifest.json").read_text(encoding="utf-8"))
    frozen = set(man.get("frozen_case_ids") or [])
    all_case = set()
    for fn in [
        "preference.jsonl",
        "retrieval_queries.jsonl",
        "conflict.jsonl",
        "forget.jsonl",
        "security.jsonl",
    ]:
        for r in load(fn):
            all_case.add(r["case_id"])
            if r.get("split") in {"validation", "final_test"} and "夹具记忆" in json.dumps(
                r, ensure_ascii=False
            ):
                # expected for frozen forget; info only for forget
                pass
    missing_frozen = sorted(frozen - all_case)
    if missing_frozen:
        add("error", "freeze", "-", f"missing frozen ids {missing_frozen[:10]}")

    # v0.4 forget: instruction vs delete semantic weak align sample
    print("=== summary ===")
    print(Counter(s for s, _, _, _ in issues))
    for sev in ("error", "warn"):
        items = [x for x in issues if x[0] == sev]
        print(f"\n--- {sev} ({len(items)}) ---")
        for s, area, cid, msg in items[:40]:
            print(f"[{s}] {area} {cid}: {msg}")
        if len(items) > 40:
            print(f"... +{len(items) - 40} more")


if __name__ == "__main__":
    main()
