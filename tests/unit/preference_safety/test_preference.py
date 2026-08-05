"""PreferenceService tests — extract, upsert, resolve, history."""
from modules.preference_safety.preference_service import PreferenceService


class TestExtract:
    def test_extract_theme_dark(self):
        ps = PreferenceService()
        events = [{"text": "\u6211\u559c\u6b22\u6df1\u8272\u4e3b\u9898", "user_id": "u1", "scene": "desktop"}]
        candidates = ps.extract(events)
        assert any(c["preference_key"] == "theme" and c["value"] == "dark" for c in candidates)

    def test_extract_tool_editor(self):
        ps = PreferenceService()
        events = [{"text": "\u6211\u5e73\u65f6\u7528VS Code\u5199Python", "user_id": "u1"}]
        candidates = ps.extract(events)
        keys = {c["preference_key"] for c in candidates}
        assert "editor" in keys or "language" in keys

    def test_extract_security_firewall(self):
        ps = PreferenceService()
        events = [{"text": "\u7cfb\u7edf\u5fc5\u987b\u5f00\u542f\u9632\u706b\u5899", "user_id": "u1"}]
        candidates = ps.extract(events)
        assert any(c["preference_key"] == "firewall" for c in candidates)

    def test_extract_empty_text_no_results(self):
        ps = PreferenceService()
        candidates = ps.extract([{"text": "", "user_id": "u1"}])
        assert len(candidates) == 0

    def test_extract_batch_events(self):
        ps = PreferenceService()
        events = [
            {"text": "\u6df1\u8272\u4e3b\u9898\u66f4\u597d\u770b", "user_id": "u1"},
            {"text": "\u542f\u7528\u9632\u706b\u5899\u5b89\u5168", "user_id": "u1"},
            {"text": "\u7528vim\u7f16\u8f91\u4ee3\u7801", "user_id": "u1"},
        ]
        candidates = ps.extract(events)
        assert len(candidates) >= 3


class TestUpsert:
    def test_insert_new(self):
        ps = PreferenceService()
        records = ps.upsert([{
            "preference_key": "theme", "value": "dark", "category": "ui",
            "confidence": 0.9, "scope": "global",
            "source_event_id": "evt_1", "scene": "desktop",
        }])
        assert len(records) == 1
        assert records[0]["revision"] == 1

    def test_update_existing(self):
        ps = PreferenceService()
        ps.upsert([{"preference_key": "theme", "value": "dark", "category": "ui",
                     "confidence": 0.9, "source_event_id": "evt_1"}])
        records = ps.upsert([{"preference_key": "theme", "value": "light", "category": "ui",
                               "confidence": 0.8, "source_event_id": "evt_2"}])
        assert records[0]["revision"] == 2
        assert records[0]["value"] == "light"

    def test_evidence_accumulates(self):
        ps = PreferenceService()
        ps.upsert([{"preference_key": "editor", "value": "vim", "category": "tool",
                     "confidence": 0.8, "source_event_id": "evt_1"}])
        records = ps.upsert([{"preference_key": "editor", "value": "vim", "category": "tool",
                               "confidence": 0.9, "source_event_id": "evt_2"}])
        assert records[0]["evidence_count"] == 2


class TestResolve:
    def test_resolve_all(self):
        ps = PreferenceService()
        ps.upsert([{"preference_key": "theme", "value": "dark", "category": "ui",
                     "confidence": 0.9, "source_event_id": "e1"}])
        ps.upsert([{"preference_key": "editor", "value": "vim", "category": "tool",
                     "confidence": 0.8, "source_event_id": "e2"}])
        results = ps.resolve()
        assert len(results) == 2

    def test_resolve_by_keys(self):
        ps = PreferenceService()
        ps.upsert([{"preference_key": "theme", "value": "dark", "category": "ui",
                     "confidence": 0.9, "source_event_id": "e1"}])
        ps.upsert([{"preference_key": "editor", "value": "vim", "category": "tool",
                     "confidence": 0.8, "source_event_id": "e2"}])
        results = ps.resolve(keys=["theme"])
        assert len(results) == 1
        assert results[0]["preference_key"] == "theme"


class TestHistory:
    def test_history_versions(self):
        ps = PreferenceService()
        ps.upsert([{"preference_key": "theme", "value": "dark", "category": "ui",
                     "confidence": 0.9, "source_event_id": "e1", "user_id": "u1"}])
        ps.upsert([{"preference_key": "theme", "value": "light", "category": "ui",
                     "confidence": 0.8, "source_event_id": "e2", "user_id": "u1"}])
        versions = ps.history(user_id="u1", preference_key="theme")
        assert len(versions) == 2

    def test_history_nonexistent(self):
        ps = PreferenceService()
        assert ps.history(user_id="u1", preference_key="nonexistent") == []

    def test_user_isolation(self):
        ps = PreferenceService()
        ps.upsert([{"preference_key": "theme", "value": "dark", "category": "ui",
                     "confidence": 0.9, "source_event_id": "e1", "user_id": "uA"}])
        ps.upsert([{"preference_key": "theme", "value": "light", "category": "ui",
                     "confidence": 0.8, "source_event_id": "e2", "user_id": "uB"}])
        rA = ps.resolve(user_id="uA", keys=["theme"])
        rB = ps.resolve(user_id="uB", keys=["theme"])
        assert len(rA) == 1 and rA[0]["value"] == "dark"
        assert len(rB) == 1 and rB[0]["value"] == "light"
