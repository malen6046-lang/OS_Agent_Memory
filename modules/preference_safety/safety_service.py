"""SafetyService — PII detection and sensitive content filtering.

Based on C++ OSMemory::detectSensitive()
"""
from __future__ import annotations

import re


class SafetyService:
    # Patterns from C++ implementation + regex refinement
    PHONE = re.compile(r"1[3-9]\d{9}")
    ID_CARD = re.compile(r"\d{17}[\dXx]")
    BANK_CARD = re.compile(r"\d{16,19}")
    EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    API_KEY = re.compile(r"(sk|api[_-]?key|token)[=:]\s*[\w-]{20,}", re.IGNORECASE)
    PASSWORD = re.compile(r"(password|pwd|密码|口令)[=:：]\s*\S+", re.IGNORECASE)

    SENSITIVE_KWS = [
        "身份证", "银行卡", "社保号", "护照号", "军官证",
        "家庭住址", "身份证号", "手机号码", "银行卡号",
        "root密码", "admin密码", "administrator",
    ]

    def __init__(self):
        pass

    def check(self, text: str) -> dict:
        entities = []
        # Phone
        for m in self.PHONE.finditer(text):
            entities.append({"type": "phone", "value": m.group(), "start": m.start(), "end": m.end()})
        # ID card
        for m in self.ID_CARD.finditer(text):
            entities.append({"type": "id_card", "value": m.group(), "start": m.start(), "end": m.end()})
        # Bank card
        for m in self.BANK_CARD.finditer(text):
            entities.append({"type": "bank_card", "value": m.group(), "start": m.start(), "end": m.end()})
        # Email
        for m in self.EMAIL.finditer(text):
            entities.append({"type": "email", "value": m.group(), "start": m.start(), "end": m.end()})
        # API key
        for m in self.API_KEY.finditer(text):
            entities.append({"type": "api_key", "value": m.group(), "start": m.start(), "end": m.end()})
        # Password-like
        for m in self.PASSWORD.finditer(text):
            entities.append({"type": "password", "value": m.group(), "start": m.start(), "end": m.end()})
        # Keyword match
        for kw in self.SENSITIVE_KWS:
            pos = text.find(kw)
            if pos >= 0:
                entities.append({"type": "sensitive_keyword", "value": kw, "start": pos, "end": pos + len(kw)})

        has_sensitive = len(entities) > 0
        return {
            "has_sensitive": has_sensitive,
            "block": has_sensitive,
            "entities": entities,
        }

    def check_batch(self, texts: list[str]) -> list[dict]:
        return [self.check(t) for t in texts]
