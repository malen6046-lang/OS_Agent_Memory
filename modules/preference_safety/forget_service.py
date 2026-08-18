"""Two-stage forget planning with no storage or vector side effects."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from contracts.schemas.forget import (
    ForgetCandidate,
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)

from .errors import (
    ConfirmationExpiredError,
    ConfirmationInvalidError,
    ForgetAuthorizationError,
    ForgetSelectionError,
)


CandidateResolver = Callable[
    [str, str],
    Iterable[ForgetCandidate | Mapping[str, Any] | str],
]


@dataclass
class _PlanState:
    plan_id: str
    user_id: str
    candidate_ids: tuple[str, ...]
    expires_at: datetime
    execution_request_id: str | None = None
    execution_ids: tuple[str, ...] | None = None


class ForgetService:
    """Create and validate precise deletion intents.

    Explicit ``memory_ids`` work independently.  Natural-language candidate
    lookup is available only when a synchronous, user-scoped resolver is
    injected; the service never calls repositories or vector stores itself.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 300,
        candidate_resolver: CandidateResolver | None = None,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        plan_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._candidate_resolver = candidate_resolver
        self._clock = clock or _utc_now
        self._token_factory = token_factory or _new_token
        self._plan_id_factory = plan_id_factory or _new_plan_id
        self._plans: dict[bytes, _PlanState] = {}
        self._lock = RLock()

    def preview(self, request: ForgetPreviewRequest) -> ForgetPlan:
        """Return candidates and a user-bound confirmation token."""
        validated = ForgetPreviewRequest.model_validate(request)
        now = self._now()
        candidates = self._resolve_candidates(validated)
        risk_level = _plan_risk(validated.instruction, len(candidates))
        candidates = [
            candidate.model_copy(
                update={"risk_level": _max_risk(candidate.risk_level, risk_level)}
            )
            for candidate in candidates
        ]
        plan_id = self._plan_id_factory()
        token = self._token_factory()
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise ValueError("plan_id_factory must return a non-empty string")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("token_factory must return a non-empty string")
        plan_id = plan_id.strip()
        token = token.strip()
        expires_at = now + self._ttl
        state = _PlanState(
            plan_id=plan_id,
            user_id=validated.user_id,
            candidate_ids=tuple(
                candidate.memory_id for candidate in candidates
            ),
            expires_at=expires_at,
        )
        plan = ForgetPlan(
            plan_id=plan_id,
            user_id=validated.user_id,
            candidates=candidates,
            risk_level=risk_level,
            confirmation_token=token,
            expires_at=expires_at,
            requires_confirmation=True,
        )

        with self._lock:
            self._drop_expired(now)
            token_key = _token_key(token)
            if token_key in self._plans:
                raise RuntimeError("token factory produced a duplicate token")
            self._plans[token_key] = state

        return plan

    def execute(self, request: ForgetExecuteRequest) -> ForgetExecutionPlan:
        """Validate a plan and return deletion intent without deleting data."""
        validated = ForgetExecuteRequest.model_validate(request)
        now = self._now()
        token_key = _token_key(validated.confirmation_token)
        selected_ids = tuple(dict.fromkeys(validated.selected_ids))

        with self._lock:
            state = self._plans.get(token_key)
            if state is None:
                raise ConfirmationInvalidError(
                    "confirmation token is invalid"
                )
            if now >= state.expires_at:
                self._plans.pop(token_key, None)
                raise ConfirmationExpiredError(
                    "confirmation token has expired"
                )
            if validated.user_id != state.user_id:
                raise ForgetAuthorizationError(
                    "forget plan belongs to another user"
                )
            if validated.plan_id != state.plan_id:
                raise ConfirmationInvalidError(
                    "confirmation token does not match the plan"
                )
            if not set(selected_ids).issubset(state.candidate_ids):
                raise ForgetSelectionError(
                    "selected_ids must be previewed candidates"
                )

            if state.execution_request_id is None:
                state.execution_request_id = validated.request_id
                state.execution_ids = selected_ids
            elif (
                state.execution_request_id != validated.request_id
                or state.execution_ids != selected_ids
            ):
                raise ConfirmationInvalidError(
                    "confirmation token is already bound to another execution"
                )

            return ForgetExecutionPlan(
                request_id=validated.request_id,
                user_id=validated.user_id,
                plan_id=validated.plan_id,
                memory_ids=list(selected_ids),
                expires_at=state.expires_at,
            )

    def _resolve_candidates(
        self,
        request: ForgetPreviewRequest,
    ) -> list[ForgetCandidate]:
        candidates = [
            ForgetCandidate(memory_id=memory_id, user_id=request.user_id)
            for memory_id in request.memory_ids
        ]
        keyword = _parse_keyword(request.instruction or "")
        if keyword and self._candidate_resolver is not None:
            for item in self._candidate_resolver(request.user_id, keyword):
                candidate = _candidate(item, request.user_id)
                if candidate.user_id == request.user_id:
                    candidates.append(candidate)

        unique: dict[str, ForgetCandidate] = {}
        for candidate in candidates:
            existing = unique.get(candidate.memory_id)
            if existing is None:
                unique[candidate.memory_id] = candidate
            else:
                unique[candidate.memory_id] = existing.model_copy(
                    update={
                        "risk_level": _max_risk(
                            existing.risk_level,
                            candidate.risk_level,
                        )
                    }
                )
        return list(unique.values())

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)

    def _drop_expired(self, now: datetime) -> None:
        expired = [
            token_key
            for token_key, state in self._plans.items()
            if now >= state.expires_at
        ]
        for token_key in expired:
            self._plans.pop(token_key, None)


def _candidate(
    item: ForgetCandidate | Mapping[str, Any] | str,
    user_id: str,
) -> ForgetCandidate:
    if isinstance(item, str):
        return ForgetCandidate(memory_id=item, user_id=user_id)
    if isinstance(item, Mapping):
        data = dict(item)
        data.setdefault("user_id", user_id)
        return ForgetCandidate.model_validate(data)
    return ForgetCandidate.model_validate(item)


def _plan_risk(
    instruction: str | None,
    candidate_count: int,
) -> str:
    text = instruction or ""
    if any(word in text for word in ("全部", "所有", "一切")):
        return "high"
    if candidate_count > 10:
        return "high"
    if candidate_count > 5:
        return "medium"
    return "low"


def _max_risk(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order[left] >= order[right] else right


def _parse_keyword(instruction: str) -> str:
    """Preserve the donor's Chinese forget-instruction parsing behavior."""
    if any(word in instruction for word in ("全部", "所有", "一切")):
        return "全部"

    forget_position = instruction.find("忘记")
    if forget_position >= 0:
        about_position = instruction.find("关于", forget_position)
        if about_position >= 0:
            return _strip_suffixes(instruction[about_position + 2 :].strip())

    delete_position = instruction.find("删除")
    if delete_position >= 0:
        related_position = instruction.find("相关", delete_position)
        if related_position >= 0:
            return _strip_suffixes(
                instruction[delete_position + 2 : related_position].strip()
            )

    verb_position = -1
    verb_length = 0
    for verb in ("不记得", "忘记", "忘了", "忘掉", "删除"):
        position = instruction.find(verb)
        if position >= 0 and (
            verb_position == -1 or position < verb_position
        ):
            verb_position = position
            verb_length = len(verb)
    if verb_position >= 0:
        remainder = instruction[verb_position + verb_length :].strip()
        remainder = remainder.lstrip("了").strip()
        if remainder.startswith("关于"):
            remainder = remainder[2:].strip()
        return _strip_suffixes(remainder) if remainder else ""
    return _strip_suffixes(instruction.strip())


def _strip_suffixes(keyword: str) -> str:
    for suffix in (
        "相关数据",
        "相关设置",
        "的配置",
        "的记录",
        "的设置",
        "的记忆",
        "的偏好",
        "的内容",
        "的资料",
        "相关",
        "的",
    ):
        if keyword.endswith(suffix):
            return keyword[: -len(suffix)].strip()
    return keyword.strip()


def _token_key(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _new_token() -> str:
    return f"confirm_{secrets.token_urlsafe(24)}"


def _new_plan_id() -> str:
    return f"forget_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
