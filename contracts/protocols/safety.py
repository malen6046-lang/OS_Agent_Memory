"""Safety service Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.envelope import Envelope
from contracts.schemas.safety import SafetyCheckResult


class SafetyService(Protocol):
    def check(self, envelope: Envelope) -> SafetyCheckResult: ...
