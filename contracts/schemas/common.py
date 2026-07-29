"""Shared schema types fixed by Module Interface Plan V1.2."""

from enum import Enum
from typing import Annotated

from pydantic import StringConstraints


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Source(str, Enum):
    TOOL_RESULT = "tool_result"
    USER_BEHAVIOR = "user_behavior"
    MANUAL_CONFIG = "manual_config"
    CROSS_SCENE = "cross_scene"


class MemoryKind(str, Enum):
    PREFERENCE = "preference"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class MemorySubtype(str, Enum):
    OUTPUT_STYLE = "output_style"
    OPERATION_HABIT = "operation_habit"
    SECURITY_POLICY = "security_policy"
    WORKFLOW = "workflow"
    CASE = "case"
    TEMPLATE = "template"
    FACT = "fact"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    TOMBSTONED = "tombstoned"
    EXPIRED = "expired"
    PENDING_REVIEW = "pending_review"


class PreferenceScope(str, Enum):
    GLOBAL = "global"
    SCENE = "scene"
    TOOL = "tool"


class PreferencePolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
