"""ForgetService — 自然语言驱动的精准遗忘。

Based on C++ OSMemory::forgetByInstruction():
  - Parse natural language ("忘记关于X的记忆", "删除X相关数据", "忘记全部")
  - Preview: return candidate memory_ids + risk level + confirmation_token
  - Execute: confirmation_token → tombstone + vector delete + audit
"""
from __future__ import annotations

import uuid
from typing import Any


class ForgetService:
    def __init__(self):
        self._tokens: dict[str, dict] = {}  # token -> {scope, candidates, created_at, expires_at}

    def preview(self, instruction: str, retriever: Any = None, user_id: str = "") -> dict:
        """Parse instruction and return ForgetPlan with confirmation_token."""
        import time

        kw = self._parse_keyword(instruction)
        scope = self._parse_scope(instruction, kw)

        candidates: list[dict] = []
        if retriever and kw:
            results = retriever.search({"query": kw, "user_id": user_id, "top_k": 20})
            for item in results.get("items", []):
                candidates.append({
                    "memory_id": item["memory_id"],
                    "content_text": item.get("content_text", "")[:100],
                    "score": item["score"],
                })

        risk = "low"
        if scope == "all" or len(candidates) > 10:
            risk = "high"
        elif len(candidates) > 5:
            risk = "medium"

        token = f"confirm_{uuid.uuid4().hex[:12]}"
        now = time.time()
        self._tokens[token] = {
            "scope": scope,
            "keyword": kw,
            "candidates": [c["memory_id"] for c in candidates],
            "created_at": now,
            "expires_at": now + 300,  # 5 min TTL
            "instruction": instruction,
        }

        return {
            "instruction": instruction,
            "scope": scope,
            "keyword": kw,
            "candidates": candidates,
            "risk_level": risk,
            "confirmation_token": token,
            "total_candidates": len(candidates),
        }

    def execute(self, confirmation_token: str, selected_ids: list[str] | None = None,
                vector_store: Any = None, metadata_store: dict | None = None) -> dict:
        """Execute forget with confirmation token."""
        import time

        token_data = self._tokens.get(confirmation_token)
        if not token_data:
            return {"success": False, "error": "token_not_found"}
        if time.time() > token_data["expires_at"]:
            del self._tokens[confirmation_token]
            return {"success": False, "error": "token_expired"}

        target_ids = selected_ids or token_data["candidates"]
        tombstoned = 0
        vectors_deleted = 0
        errors = []

        for mid in target_ids:
            # Mark as tombstoned in metadata
            if metadata_store and mid in metadata_store:
                metadata_store[mid]["status"] = "tombstoned"
                tombstoned += 1

        # Delete from vector store
        if vector_store and target_ids:
            try:
                import hashlib
                pks = [int(hashlib.md5(mid.encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
                       for mid in target_ids]
                result = vector_store.delete(pks)
                vectors_deleted = result.get("deleted", 0)
            except Exception as e:
                errors.append(f"vector_delete: {e}")

        del self._tokens[confirmation_token]
        return {
            "success": True,
            "tombstoned": tombstoned,
            "vectors_deleted": vectors_deleted,
            "total_deleted": len(target_ids),
            "errors": errors or None,
        }

    def _parse_keyword(self, instruction: str) -> str:
        """Extract keyword from natural language forget instruction."""
        # "忘记关于X的记忆" → X
        p = instruction.find("忘记")
        if p >= 0:
            q = instruction.find("关于", p)
            if q >= 0:
                r = instruction.find("的记忆", q)
                if r >= 0:
                    return instruction[q + 2 : r].strip()
                r = instruction.find("的偏好", q)
                if r >= 0:
                    return instruction[q + 2 : r].strip()
                # "忘记X" after 忘记
                remaining = instruction[p + 2:].strip()
                if remaining and len(remaining) < 20:
                    return remaining
        # "删除X相关" → X
        p = instruction.find("删除")
        if p >= 0:
            q = instruction.find("相关", p)
            if q >= 0:
                return instruction[p + 2 : q].strip()
            remaining = instruction[p + 2:].strip()
            if remaining and len(remaining) < 20:
                return remaining
        return instruction.strip()

    def _parse_scope(self, instruction: str, keyword: str) -> str:
        """Determine scope: user, topic, or all."""
        if any(w in instruction for w in ["全部", "所有", "一切"]):
            return "all"
        if keyword and len(keyword) > 10:
            return "specific"
        return "topic"
