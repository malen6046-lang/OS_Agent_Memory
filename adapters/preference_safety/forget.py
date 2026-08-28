"""Safe two-stage ForgetService with V1.2 intent parsing and reranking."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from contracts.schemas.common import MemoryStatus
from contracts.schemas.forget import (
    ForgetCandidate,
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)
from contracts.schemas.retrieval import SearchRequest, SearchResponse
from modules.preference_safety.algorithm_v1_1.forget_service import (
    ForgetService as LegacyForgetService,
)
from modules.preference_safety.forget_intent_v1_2 import (
    ForgetIntent,
    matches_scope_qualifier,
    parse_forget_intent,
    select_relevant_candidates,
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


class ForgetServiceAdapter:
    """Build a precise preview; storage mutation remains in Orchestrator."""

    def __init__(
        self,
        *,
        legacy_factory: Callable[[], Any] = LegacyForgetService,
        candidate_resolver: CandidateResolver | None = None,
        ttl_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        plan_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._legacy_factory = legacy_factory
        self._candidate_resolver = candidate_resolver
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or _utc_now
        self._token_factory = token_factory or _new_token
        self._plan_id_factory = plan_id_factory or _new_plan_id
        self._plans: dict[bytes, _PlanState] = {}
        self._lock = RLock()

    def preview(self, request: ForgetPreviewRequest) -> ForgetPlan:
        validated = ForgetPreviewRequest.model_validate(request)
        intent = parse_forget_intent(validated.instruction or "")
        retriever = (
            _ResolverRetriever(self._candidate_resolver, intent)
            if self._candidate_resolver is not None
            else None
        )
        legacy = self._legacy_factory()
        raw = legacy.preview(
            validated.instruction or "",
            retriever=retriever,
            user_id=validated.user_id,
            metadata_store=None,
        )
        if not isinstance(raw, Mapping):
            raise TypeError("legacy forget preview must return a mapping")

        candidate_ids = list(dict.fromkeys(validated.memory_ids))
        raw_candidates = raw.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise TypeError("legacy forget candidates must be a list")
        for item in raw_candidates:
            if not isinstance(item, Mapping):
                raise TypeError("legacy forget candidate must be a mapping")
            memory_id = item.get("memory_id")
            if (
                isinstance(memory_id, str)
                and memory_id.strip()
                and memory_id.strip() not in candidate_ids
            ):
                candidate_ids.append(memory_id.strip())

        legacy_risk = _legacy_risk(raw.get("risk_level"))
        if intent.scope == "all" and intent.target:
            legacy_risk = "low"
        risk_level = _max_risk(
            legacy_risk,
            _request_risk(validated.instruction, len(candidate_ids)),
        )
        candidates = [
            ForgetCandidate(
                memory_id=memory_id,
                user_id=validated.user_id,
                risk_level=risk_level,
            )
            for memory_id in candidate_ids
        ]
        now = self._now()
        expires_at = now + self._ttl
        plan_id = _factory_string(self._plan_id_factory(), "plan_id")
        token = _factory_string(
            self._token_factory(),
            "confirmation_token",
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
        state = _PlanState(
            plan_id=plan_id,
            user_id=validated.user_id,
            candidate_ids=tuple(candidate_ids),
            expires_at=expires_at,
        )
        with self._lock:
            self._drop_expired(now)
            token_key = _token_key(token)
            if token_key in self._plans:
                raise RuntimeError("token factory produced a duplicate token")
            self._plans[token_key] = state
        return plan

    def execute(
        self,
        request: ForgetExecuteRequest,
    ) -> ForgetExecutionPlan:
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

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)

    def _drop_expired(self, now: datetime) -> None:
        expired = [
            key
            for key, state in self._plans.items()
            if now >= state.expires_at
        ]
        for key in expired:
            self._plans.pop(key, None)


class _ResolverRetriever:
    """Expose a user-scoped resolver through the legacy retriever shape."""

    def __init__(self, resolver: CandidateResolver, intent: ForgetIntent) -> None:
        self._resolver = resolver
        self._intent = intent

    def search(self, request: Mapping[str, Any]) -> dict[str, list[dict]]:
        user_id = str(request.get("user_id", ""))
        keyword = self._intent.resolver_query or str(request.get("query", ""))
        items: list[dict[str, Any]] = []
        for raw in self._resolver(user_id, keyword):
            item = _resolver_item(raw, user_id)
            if item is not None and not any(
                matches_scope_qualifier(exclusion, item)
                for exclusion in self._intent.exclusions
            ):
                items.append(item)
        return {"items": items}


def build_forget_service(
    retriever: Any = None,
    config: Any = None,
    app_config: Any = None,
) -> ForgetServiceAdapter:
    """Create the synchronous ForgetService implementation for DI."""
    del config, app_config
    resolver = (
        _candidate_resolver_from_retriever(retriever)
        if retriever is not None
        else None
    )
    return ForgetServiceAdapter(candidate_resolver=resolver)


def _candidate_resolver_from_retriever(
    retriever: Any,
) -> CandidateResolver:
    search = getattr(retriever, "search", None)
    if not callable(search):
        raise TypeError("retriever must provide a callable search method")

    def resolve(user_id: str, keyword: str) -> list[dict[str, Any]]:
        query = keyword.strip()
        if not query:
            return []
        if query == "__all__" or query.startswith("__all__:"):
            list_active = getattr(retriever, "list_active_candidates", None)
            if not callable(list_active):
                return []
            rows = [dict(item) for item in list_active(user_id)]
            qualifier = query.partition(":")[2].strip()
            if qualifier:
                rows = [
                    item
                    for item in rows
                    if matches_scope_qualifier(qualifier, item)
                ]
            return rows
        digest = hashlib.blake2b(
            f"{user_id}\0{query}".encode("utf-8"),
            digest_size=8,
            person=b"forget-preview",
        ).hexdigest()
        request = SearchRequest(
            request_id=f"req_forget_preview_{digest}",
            user_id=user_id,
            query=query,
            top_k=20,
        )
        response = SearchResponse.model_validate(search(request))
        if response.user_id != user_id:
            return []
        candidates = [
            {
                "memory_id": item.memory_id,
                "user_id": item.user_id,
                "content_text": item.content_text,
                "score": item.score,
            }
            for item in response.items
            if item.user_id == user_id
            and item.status is MemoryStatus.ACTIVE
        ]
        return select_relevant_candidates(
            query,
            candidates,
            degraded=response.degraded,
        )

    return resolve


def _resolver_item(raw: Any, user_id: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        memory_id = raw
        owner = user_id
        content_text = ""
        score = 1.0
    elif isinstance(raw, ForgetCandidate):
        memory_id = raw.memory_id
        owner = raw.user_id
        content_text = ""
        score = 1.0
    elif isinstance(raw, Mapping):
        memory_id = raw.get("memory_id")
        owner = raw.get("user_id", user_id)
        content_text = raw.get("content_text", "")
        score = raw.get("score", 1.0)
    else:
        raise TypeError("candidate resolver returned an unsupported item")

    if owner != user_id:
        return None
    if not isinstance(memory_id, str) or not memory_id.strip():
        raise TypeError("candidate resolver returned an invalid memory_id")
    return {
        "memory_id": memory_id.strip(),
        "content_text": str(content_text),
        "score": float(score),
    }


def _request_risk(instruction: str | None, candidate_count: int) -> str:
    intent = parse_forget_intent(instruction or "")
    if intent.scope == "all":
        return "medium" if intent.target else "high"
    if any(
        cue in intent.target.casefold()
        for cue in (
            "密码",
            "口令",
            "私钥",
            "令牌",
            "token",
            "api key",
            "api_key",
            "身份证",
            "银行卡",
        )
    ):
        return "high"
    if intent.exclusions:
        return "medium"
    if candidate_count > 10:
        return "high"
    if candidate_count > 5:
        return "medium"
    return "low"


def _legacy_risk(value: Any) -> str:
    return value if value in {"low", "medium", "high"} else "low"


def _max_risk(left: str, right: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return left if rank[left] >= rank[right] else right


def _factory_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} factory must return a non-empty string")
    return value.strip()


def _token_key(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _new_token() -> str:
    return f"confirm_{secrets.token_urlsafe(24)}"


def _new_plan_id() -> str:
    return f"forget_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
