"""Preference service Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.envelope import Envelope
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord


class PreferenceService(Protocol):
    def extract(self, events: list[Envelope]) -> list[PreferenceCandidate]: ...

    def upsert(
        self, candidates: list[PreferenceCandidate]
    ) -> list[PreferenceRecord]: ...
    def resolve(
        self,
        user_id: str,
        scene: str,
        keys: list[str] | None = None,
    ) -> list[PreferenceRecord]: ...

    def history(
        self, user_id: str, preference_key: str
    ) -> list[PreferenceRecord]: ...
