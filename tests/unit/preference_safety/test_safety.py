"""SafetyService tests — PII detection."""
from modules.preference_safety.safety_service import SafetyService


class TestPII:
    def test_phone_detected(self):
        ss = SafetyService()
        r = ss.check("\u6211\u7684\u7535\u8bdd\u662f13812345678")
        assert r["has_sensitive"] is True
        assert any(e["type"] == "phone" for e in r["entities"])

    def test_id_card_detected(self):
        ss = SafetyService()
        r = ss.check("\u8eab\u4efd\u8bc1\u53f71101011990010112345X")
        assert r["has_sensitive"] is True
        assert any(e["type"] == "id_card" for e in r["entities"])

    def test_email_detected(self):
        ss = SafetyService()
        r = ss.check("contact me at test@example.com")
        assert r["has_sensitive"] is True
        assert any(e["type"] == "email" for e in r["entities"])

    def test_bank_card_detected(self):
        ss = SafetyService()
        r = ss.check("\u5361\u53f7622512345678901234")
        assert r["has_sensitive"] is True
        assert any(e["type"] == "bank_card" for e in r["entities"])

    def test_api_key_detected(self):
        ss = SafetyService()
        r = ss.check("sk=abcdefghijklmnopqrstuvwxyz123")
        assert r["has_sensitive"] is True

    def test_password_detected(self):
        ss = SafetyService()
        r = ss.check("password=admin123456")
        assert r["has_sensitive"] is True

    def test_keyword_detected(self):
        ss = SafetyService()
        r = ss.check("\u8bf7\u63d0\u4f9b\u60a8\u7684\u8eab\u4efd\u8bc1\u53f7")
        assert r["has_sensitive"] is True

    def test_safe_text(self):
        ss = SafetyService()
        r = ss.check("Ctrl+Alt+T\u6253\u5f00\u7ec8\u7aef")
        assert r["has_sensitive"] is False


class TestBatch:
    def test_batch_check(self):
        ss = SafetyService()
        results = ss.check_batch([
            "hello world",
            "\u7535\u8bdd13800000000",
            "test@test.com",
        ])
        assert results[0]["has_sensitive"] is False
        assert results[1]["has_sensitive"] is True
        assert results[2]["has_sensitive"] is True
