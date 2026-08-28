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

    def preview(self, instruction: str, retriever: Any = None, user_id: str = "", metadata_store: dict | None = None) -> dict:
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
        candidate_ids = [c["memory_id"] for c in candidates]
        self._tokens[token] = {
            "scope": scope,
            "keyword": kw,
            "user_id": user_id,
            "candidates": candidate_ids,
            "created_at": now,
            "expires_at": now + 300,
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
                user_id: str = "", vector_store: Any = None,
                metadata_store: dict | None = None) -> dict:
        """Execute forget with confirmation token."""
        import time

        token_data = self._tokens.get(confirmation_token)
        if not token_data:
            return {"success": False, "error": "token_not_found"}
        if time.time() > token_data["expires_at"]:
            del self._tokens[confirmation_token]
            return {"success": False, "error": "token_expired"}
        if user_id and token_data.get("user_id") and token_data["user_id"] != user_id:
            return {"success": False, "error": "unauthorized_user"}

        target_ids = selected_ids or token_data["candidates"]
        if selected_ids:
            allowed = set(selected_ids)
            candidates_set = set(token_data["candidates"])
            if not allowed.issubset(candidates_set):
                return {"success": False, "error": "selected_ids not in preview candidates"}
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

    SUFFIXES = [
        "的配置", "的记录", "的设置", "的记忆", "的偏好",
        "的相关", "相关数据", "相关设置", "的内容", "的资料",
    ]

    def _parse_keyword(self, instruction: str) -> str:
        """Extract keyword from natural language forget instruction."""
        if any(w in instruction for w in ["全部", "所有", "一切"]):
            return "全部"
        # "忘记关于X的记忆/偏好" → X
        p = instruction.find("忘记")
        if p >= 0:
            q = instruction.find("关于", p)
            if q >= 0:
                return self._strip_suffixes(instruction[q + 2 :].strip())
        # "删除X相关Y" → X
        p = instruction.find("删除")
        if p >= 0:
            q = instruction.find("相关", p)
            if q >= 0:
                return self._strip_suffixes(instruction[p + 2 : q].strip())
        # 动词定位: 忘记/忘了/不记得/忘掉/删除 后的内容
        verb_idx, verb_len = -1, 0
        for v in ["不记得", "忘记", "忘了", "忘掉", "删除"]:
            idx = instruction.find(v)
            if idx >= 0 and (verb_idx == -1 or idx < verb_idx):
                verb_idx, verb_len = idx, len(v)
        if verb_idx >= 0:
            after = instruction[verb_idx + verb_len :].strip().lstrip("了").strip()
            if after.startswith("关于"):
                after = after[2:].strip()
            return self._strip_suffixes(after) if after else ""
        return self._strip_suffixes(instruction.strip())

    def _strip_suffixes(self, kw: str) -> str:
        """Strip common trailing qualifiers like "的配置"/"的记录"/"相关的"."""
        # 去掉尾部"相关的/相关"
        for tail in ["相关", "的", "的记忆", "的偏好", "的设置", "的配置", "的记录"]:
            if kw.endswith(tail):
                kw = kw[: -len(tail)].strip()
                break
        return kw.strip()

    def _parse_scope(self, instruction: str, keyword: str) -> str:
        """Determine scope: user, topic, or all."""
        if any(w in instruction for w in ["全部", "所有", "一切"]):
            return "all"
        if keyword and len(keyword) > 10:
            return "specific"
        return "topic"
