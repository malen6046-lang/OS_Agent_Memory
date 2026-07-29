import pytest
from pydantic import TypeAdapter, ValidationError

from contracts.schemas.common import (
    MemoryKind,
    MemoryStatus,
    MemorySubtype,
    PreferencePolarity,
    PreferenceScope,
    Source,
)


@pytest.mark.parametrize(
    ("enum_type", "values"),
    [
        (
            Source,
            {"tool_result", "user_behavior", "manual_config", "cross_scene"},
        ),
        (
            MemoryKind,
            {"preference", "semantic", "episodic", "procedural"},
        ),
        (
            MemorySubtype,
            {
                "output_style",
                "operation_habit",
                "security_policy",
                "workflow",
                "case",
                "template",
                "fact",
            },
        ),
        (
            MemoryStatus,
            {
                "active",
                "superseded",
                "tombstoned",
                "expired",
                "pending_review",
            },
        ),
        (PreferenceScope, {"global", "scene", "tool"}),
        (PreferencePolarity, {"positive", "negative"}),
    ],
)
def test_public_enum_values(enum_type, values):
    assert {member.value for member in enum_type} == values


@pytest.mark.parametrize(
    "enum_type",
    [
        Source,
        MemoryKind,
        MemorySubtype,
        MemoryStatus,
        PreferenceScope,
        PreferencePolarity,
    ],
)
def test_public_enums_reject_unknown_value(enum_type):
    with pytest.raises(ValidationError):
        TypeAdapter(enum_type).validate_python("unknown")
