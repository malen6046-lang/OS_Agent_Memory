# -*- coding: utf-8 -*-
"""Fix 5 dev conflict GT issues reported in DATASET_ISSUES.md."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFLICT = ROOT / "evaluation" / "dataset" / "conflict.jsonl"


def normalize_content(o: dict, side: str) -> None:
    c = o[side].get("content", {})
    if c and "preference_key" not in c and len(c) == 1:
        k, v = next(iter(c.items()))
        o[side]["content"] = {"preference_key": k, "value": v}
        label = "旧记忆" if side == "old" else "新记忆"
        o[side]["content_text"] = f"{label}：{k}={v}"


def main() -> None:
    rows: list[str] = []
    with CONFLICT.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            cid = o["case_id"]

            if cid == "CONF-0014":
                o["new"]["subtype"] = "security_policy"

            elif cid == "CONF-0024":
                o["old"]["content"] = {"preference_key": "tool.office", "value": "libreoffice"}
                o["new"]["content"] = {"preference_key": "tool.office", "value": "wps"}
                o["old"]["content_text"] = "旧记忆：tool.office=libreoffice"
                o["new"]["content_text"] = "新记忆：tool.office=wps"
                o["expected"]["relation"] = "replace"
                o["expected"]["strategy"] = "keep_new"
                o["new"]["valid_from"] = "2026-07-20T15:00:00+08:00"
                o["new"]["confidence"] = 0.9

            elif cid == "CONF-0025":
                o["old"]["content"] = {"preference_key": "tool.editor", "value": "vscode"}
                o["new"]["content"] = {"preference_key": "tool.editor", "value": "kylin_ide"}
                o["old"]["content_text"] = "旧记忆：tool.editor=vscode"
                o["new"]["content_text"] = "新记忆：tool.editor=kylin_ide"
                o["expected"]["relation"] = "replace"
                o["expected"]["strategy"] = "keep_new"
                o["new"]["valid_from"] = "2026-07-20T15:00:00+08:00"
                o["new"]["confidence"] = 0.9

            elif cid == "CONF-0026":
                o["old"]["content"] = {
                    "preference_key": "workflow.backup",
                    "value": "full_local",
                }
                o["new"]["content"] = {
                    "preference_key": "workflow.backup",
                    "value": "incremental_local",
                }
                o["old"]["content_text"] = "旧记忆：workflow.backup=full_local"
                o["new"]["content_text"] = "新记忆：workflow.backup=incremental_local"
                o["expected"]["relation"] = "replace"
                o["expected"]["strategy"] = "keep_new"
                o["new"]["valid_from"] = "2026-07-20T15:00:00+08:00"
                o["new"]["confidence"] = 0.9

            elif cid == "CONF-0029":
                o["old"]["content"] = {"preference_key": "ui.theme", "value": "dark"}
                o["new"]["content"] = {"preference_key": "ui.theme", "value": "light"}
                o["old"]["content_text"] = "旧记忆：ui.theme=dark"
                o["new"]["content_text"] = "新记忆：ui.theme=light"
                o["new"]["valid_from"] = "2026-08-01T10:00:00+08:00"
                o["new"]["confidence"] = 0.92
                o["new"]["revision"] = 2

            elif cid in {"CONF-0027", "CONF-0028"}:
                normalize_content(o, "old")
                normalize_content(o, "new")

            rows.append(json.dumps(o, ensure_ascii=False))

    CONFLICT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"fixed {CONFLICT}")


if __name__ == "__main__":
    main()
