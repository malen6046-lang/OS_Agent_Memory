"""Structured conflict classifier layered over Algorithm V1.1."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from contracts.schemas.memory import MemoryRecord


_SUPPORT_CUES = (
    "日志",
    "巡检",
    "确认",
    "验证",
    "检测",
    "成功",
    "建议保持",
    "可用",
)

_MANUAL_REVIEW_CUES = (
    "场景",
    "临时",
    "仅本次",
    "例外",
)

_KNOWN_VALUE_DOMAINS = {
    "ui.theme": {"dark", "light", "system", "auto"},
    "tool.browser": {
        "firefox",
        "chrome",
        "chromium",
        "edge",
        "opera",
    },
    "tool.editor": {
        "vscode",
        "kylin_ide",
        "vim",
        "nvim",
        "emacs",
        "sublime",
    },
    "output.format": {
        "markdown",
        "pdf",
        "html",
        "text",
        "table",
        "json",
        "docx",
    },
    "output.verbosity": {
        "concise",
        "detailed",
        "step_by_step",
    },
    "security.ssh_auth": {
        "password",
        "password_or_key",
        "pubkey_only",
    },
    "workflow.backup": {
        "incremental_local",
        "incremental_cloud",
        "full_local",
        "full_cloud",
    },
}


class StructuredConflictClassifier:
    """Use frozen record fields first and legacy text heuristics as fallback."""

    def __init__(self, legacy_classifier: Any) -> None:
        self._legacy = legacy_classifier

    def classify(
        self,
        old: MemoryRecord,
        new: MemoryRecord,
    ) -> dict[str, Any]:
        old = MemoryRecord.model_validate(old)
        new = MemoryRecord.model_validate(new)
        if old.user_id != new.user_id:
            return self._result(
                "unrelated",
                "keep_old",
                1.0,
                ["different_user"],
            )

        old_key, old_value = _preference_slot(old)
        new_key, new_value = _preference_slot(new)
        if old_key and new_key:
            return self._classify_slot(
                old,
                new,
                old_key,
                old_value,
                new_key,
                new_value,
            )
        return self._fallback(old, new)

    def _classify_slot(
        self,
        old: MemoryRecord,
        new: MemoryRecord,
        old_key: str,
        old_value: Any,
        new_key: str,
        new_value: Any,
    ) -> dict[str, Any]:
        if old_key != new_key:
            return self._result(
                "unrelated",
                "keep_old",
                0.96,
                ["different_attribute"],
            )

        if old_value == new_value:
            if _has_support_evidence(new.content_text):
                return self._result(
                    "support",
                    "merge",
                    0.91,
                    ["same_attribute", "same_value", "new_evidence"],
                )
            return self._result(
                "duplicate",
                "keep_old",
                0.95,
                ["same_attribute", "same_value"],
            )

        if _value_is_clearly_foreign(old_key, new_value):
            return self._result(
                "unrelated",
                "keep_old",
                0.92,
                ["value_belongs_to_different_attribute"],
            )

        if _is_extension(old_value, new_value):
            strategy = "keep_new" if old_key.startswith("kb.") else "merge"
            return self._result(
                "extend",
                strategy,
                0.9,
                ["same_attribute", "new_value_extends_old"],
            )

        if _is_contradictory_slot(old_key):
            strategy = _contradiction_strategy(old_key, old, new)
            return self._result(
                "contradict",
                strategy,
                0.89,
                ["same_attribute", "contradictory_values"],
            )

        if _is_newer_or_stronger(old, new):
            return self._result(
                "replace",
                "keep_new",
                0.89,
                ["same_attribute", "newer_effective_at"],
            )
        return self._result(
            "contradict",
            "manual_review",
            0.82,
            ["same_attribute", "conflicting_values", "no_clear_winner"],
        )

    def _fallback(
        self,
        old: MemoryRecord,
        new: MemoryRecord,
    ) -> dict[str, Any]:
        old_text = old.content_text.strip()
        new_text = new.content_text.strip()
        if old_text == new_text:
            return self._result(
                "duplicate",
                "keep_old",
                0.95,
                ["same_text"],
            )
        score = _text_similarity(old_text, new_text)
        raw = dict(
            self._legacy.classify(
                new_text,
                new.model_dump(mode="python"),
                [
                    {
                        "score": score,
                        "meta": old.model_dump(mode="python"),
                    }
                ],
            )
        )
        if raw.get("relation") == "unrelated":
            raw["strategy"] = "keep_old"
        return raw

    @staticmethod
    def _result(
        relation: str,
        strategy: str,
        confidence: float,
        reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "relation": relation,
            "strategy": strategy,
            "confidence": confidence,
            "reasons": reasons,
        }


def _preference_slot(record: MemoryRecord) -> tuple[str | None, Any]:
    content = record.content
    key = content.get("preference_key")
    if not isinstance(key, str) or not key.strip() or "value" not in content:
        return None, None
    return key.strip(), content.get("value")


def _has_support_evidence(text: str) -> bool:
    return any(cue in text for cue in _SUPPORT_CUES)


def _is_extension(old_value: Any, new_value: Any) -> bool:
    if not isinstance(old_value, str) or not isinstance(new_value, str):
        return False
    old_normalized = old_value.strip().casefold()
    new_normalized = new_value.strip().casefold()
    if not old_normalized or old_normalized == new_normalized:
        return False
    old_tokens = {
        token
        for token in old_normalized.replace("-", "_").split("_")
        if token
    }
    new_tokens = {
        token
        for token in new_normalized.replace("-", "_").split("_")
        if token
    }
    return old_normalized in new_normalized or (
        bool(old_tokens) and old_tokens < new_tokens
    )


def _is_contradictory_slot(key: str) -> bool:
    return key == "output.verbosity" or key.startswith(
        ("security.", "fix.", "policy.")
    )


def _contradiction_strategy(
    key: str,
    old: MemoryRecord,
    new: MemoryRecord,
) -> str:
    if key == "output.verbosity":
        return "manual_review"
    if any(cue in new.content_text for cue in _MANUAL_REVIEW_CUES):
        return "manual_review"
    return "keep_new" if _is_newer_or_stronger(old, new) else "manual_review"


def _is_newer_or_stronger(old: MemoryRecord, new: MemoryRecord) -> bool:
    if new.valid_from > old.valid_from:
        return True
    return new.confidence > old.confidence


def _value_is_clearly_foreign(key: str, value: Any) -> bool:
    """Reject only values known to belong to another attribute.

    Value domains are supporting evidence, not closed-world allowlists.  An
    unseen browser or output format is therefore still a valid value for its
    slot, while a known SSH authentication value stored under ``tool.browser``
    is treated as structurally mis-keyed.
    """
    normalized = str(value).strip().casefold()
    if not normalized:
        return False
    own_domain = _KNOWN_VALUE_DOMAINS.get(key, set())
    if normalized in own_domain:
        return False
    return any(
        normalized in domain
        for other_key, domain in _KNOWN_VALUE_DOMAINS.items()
        if other_key != key
    )


def _text_similarity(old_text: str, new_text: str) -> float:
    sequence = SequenceMatcher(None, old_text, new_text).ratio()
    old_chars = set(old_text)
    new_chars = set(new_text)
    union = old_chars | new_chars
    jaccard = len(old_chars & new_chars) / len(union) if union else 0.0
    # A single changed slot (for example dark -> light) should retain its
    # strong sequence similarity. Averaging with set overlap can otherwise
    # push short CJK sentences below the donor classifier's 0.85 threshold.
    return max(0.0, min(1.0, max(sequence, jaccard)))
