"""V1.2 natural-language forget intent parsing and conservative reranking."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ForgetIntent:
    scope: Literal["topic", "all"]
    target: str
    exclusions: tuple[str, ...] = ()

    @property
    def resolver_query(self) -> str:
        if self.scope == "all":
            return f"__all__:{self.target}" if self.target else "__all__"
        return self.target


def parse_forget_intent(instruction: str) -> ForgetIntent:
    """Separate the deletion target from explicit keep clauses."""
    normalized = " ".join(str(instruction).strip().split())
    if not normalized:
        return ForgetIntent(scope="topic", target="")

    delete_clause, keep_clause = _split_keep_clause(normalized)
    exclusions = _exclusion_targets(keep_clause)

    all_scope = bool(re.search(r"(?:全部|所有|一切)", delete_clause))
    target = _clean_target(delete_clause)
    if all_scope:
        target = re.sub(r"(?:全部|所有|一切)", "", target).strip()
        target = _strip_memory_words(target)
    return ForgetIntent(
        scope="all" if all_scope else "topic",
        target=target,
        exclusions=exclusions,
    )


def select_relevant_candidates(
    target: str,
    candidates: Iterable[Mapping[str, Any]],
    *,
    degraded: bool = False,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Prefer precision for deletion previews while retaining semantic top-1."""
    query = target.strip()
    if not query:
        return []
    rows = [dict(candidate) for candidate in candidates]
    if not rows:
        return []

    ranked: list[tuple[float, float, int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        content = str(row.get("content_text", ""))
        lexical = _lexical_coverage(query, content)
        score = _finite_score(row.get("score"))
        ranked.append((lexical, score, index, row))

    best_lexical = max(item[0] for item in ranked)
    lexical_floor = max(0.34, best_lexical - 0.12)
    accepted: list[dict[str, Any]] = []
    for lexical, _score, _index, row in ranked:
        if lexical >= lexical_floor:
            accepted.append(row)

    if not accepted and not degraded:
        top_lexical, top_score, _, top_row = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        if top_lexical >= 0.2 or (
            top_score >= 0.78
            and (len(ranked) == 1 or top_score - second_score >= 0.035)
        ):
            accepted.append(top_row)

    accepted_ids = {str(row.get("memory_id", "")) for row in accepted}
    return [
        row
        for row in rows
        if str(row.get("memory_id", "")) in accepted_ids
    ][: max(1, limit)]


def matches_scope_qualifier(qualifier: str, candidate: Mapping[str, Any]) -> bool:
    """Filter a bounded all-scope request such as 'all temporary memories'."""
    target = qualifier.strip()
    if not target:
        return True
    content = str(candidate.get("content_text", ""))
    attributes = candidate.get("attributes", {})
    attribute_text = ""
    if isinstance(attributes, Mapping):
        attribute_text = " ".join(str(value) for value in attributes.values())
    return _lexical_coverage(target, f"{content} {attribute_text}") >= 0.34


def _split_keep_clause(instruction: str) -> tuple[str, str]:
    """Support both 'keep X' and natural Chinese 'X stays' clauses."""
    prefix = re.match(
        r"^(?P<delete>.+?)[，,；;]\s*(?:但是|但|同时|并且)?\s*"
        r"(?:保留|留下|不要删除|不删除|别删|勿删|不要动|别动)\s*"
        r"(?P<keep>.+?)\s*[。！!]?$",
        instruction,
    )
    if prefix:
        return prefix.group("delete").strip(), prefix.group("keep").strip()

    suffix = re.match(
        r"^(?P<delete>.+?)[，,；;]\s*(?:但是|但|同时|并且)?\s*"
        r"(?P<keep>.+?)\s*"
        r"(?:保留|留下|不要删除|不删除|别删|勿删|不要动|别动)"
        r"(?:即可|就行)?\s*[。！!]?$",
        instruction,
    )
    if suffix:
        return suffix.group("delete").strip(), suffix.group("keep").strip()
    return instruction, ""


def _exclusion_targets(keep_clause: str) -> tuple[str, ...]:
    if not keep_clause:
        return ()
    targets = (
        _clean_target(part)
        for part in re.split(r"\s*(?:、|和|及|与)\s*", keep_clause)
    )
    return tuple(dict.fromkeys(target for target in targets if target))


def _clean_target(text: str) -> str:
    cleaned = text.strip(" ，,。；;：:")
    cleaned = re.sub(
        r"^(?:请|麻烦|帮我|我要|我想)?\s*"
        r"(?:忘记|忘掉|忘了|删除|清除|移除|抹除)\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^关于\s*", "", cleaned)
    return _strip_memory_words(cleaned)


def _strip_memory_words(text: str) -> str:
    cleaned = text.strip()
    suffixes = (
        "相关的记忆",
        "相关记忆",
        "相关数据",
        "相关设置",
        "的所有记忆",
        "的记忆",
        "的偏好",
        "的配置",
        "的记录",
        "记忆",
        "数据",
        "资料",
        "相关",
        "的",
    )
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                changed = True
                break
    return cleaned


def _lexical_coverage(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    content_folded = content.casefold()
    matched = sum(_token_matches(token, content_folded) for token in query_tokens)
    return matched / len(query_tokens)


def _tokens(text: str) -> list[str]:
    folded = text.casefold()
    latin = re.findall(r"[a-z0-9][a-z0-9_.-]+", folded)
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", folded)
    cjk: list[str] = []
    for run in cjk_runs:
        parts = re.split(
            r"(?:关于|相关|记忆|内容|数据|信息|设置|配置|记录|细节|"
            r"偏好|习惯|流程|策略|和|及|与|的)",
            run,
        )
        for part in parts:
            if len(part) == 1:
                cjk.append(part)
            elif part:
                cjk.extend(
                    part[index : index + 2]
                    for index in range(len(part) - 1)
                )
    return list(dict.fromkeys([*latin, *cjk]))


def _token_matches(token: str, content_folded: str) -> bool:
    equivalents = {
        "token": ("token", "令牌"),
        "令牌": ("令牌", "token"),
    }
    return any(
        alternative in content_folded
        for alternative in equivalents.get(token, (token,))
    )


def _finite_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if score == score and abs(score) != float("inf") else 0.0
