"""ForgetService tests — natural language forget."""
from modules.preference_safety.forget_service import ForgetService


class TestPreview:
    def test_preview_keyword_extraction(self):
        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u5173\u4e8e\u7ec8\u7aef\u5feb\u6377\u952e\u7684\u8bb0\u5fc6")
        assert plan["keyword"] == "\u7ec8\u7aef\u5feb\u6377\u952e"
        assert "confirmation_token" in plan
        assert plan["scope"] in ("topic", "specific")

    def test_preview_delete_related(self):
        fs = ForgetService()
        plan = fs.preview("\u5220\u9664\u7ec8\u7aef\u76f8\u5173\u6570\u636e")
        assert plan["keyword"] == "\u7ec8\u7aef"
        assert "confirmation_token" in plan

    def test_preview_all(self):
        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u5168\u90e8\u8bb0\u5fc6")
        assert plan["scope"] == "all"
        assert plan["risk_level"] == "high"

    def test_preview_empty_instruction(self):
        fs = ForgetService()
        plan = fs.preview("")
        assert plan["keyword"] == ""
        assert plan["total_candidates"] == 0

    def test_preview_with_retriever(self):
        class FakeRetriever:
            def search(self, request):
                return {"items": [
                    {"memory_id": "m1", "content_text": "\u7ec8\u7aef\u5feb\u6377\u952e\u8bf4\u660e", "score": 0.9},
                    {"memory_id": "m2", "content_text": "\u6570\u636e\u5e93\u5907\u4efd\u65b9\u6cd5", "score": 0.3},
                ]}

        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u5173\u4e8e\u7ec8\u7aef\u7684\u8bb0\u5fc6",
                          retriever=FakeRetriever(), user_id="u1")
        assert plan["total_candidates"] == 2
        assert plan["risk_level"] in ("low", "medium")


class TestExecute:
    def test_execute_success(self):
        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u5173\u4e8e\u4e3b\u9898\u7684\u504f\u597d")
        token = plan["confirmation_token"]
        # Without selected_ids, uses preview candidates (which are empty with no retriever)
        result = fs.execute(token, selected_ids=None)
        assert result["success"] is True

    def test_execute_expired_token(self):
        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u4e3b\u9898")
        token = plan["confirmation_token"]
        fs._tokens[token]["expires_at"] = 0
        result = fs.execute(token)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_execute_invalid_token(self):
        fs = ForgetService()
        result = fs.execute("bad_token")
        assert result["success"] is False
        assert result["error"] == "token_not_found"

    def test_execute_unauthorized_user(self):
        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u4e3b\u9898", user_id="usr_A")
        result = fs.execute(plan["confirmation_token"], user_id="usr_B")
        assert result["success"] is False
        assert result["error"] == "unauthorized_user"

    def test_selected_ids_must_be_in_candidates(self):
        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u4e3b\u9898")
        result = fs.execute(plan["confirmation_token"], selected_ids=["not_in_preview"])
        assert result["success"] is False

    def test_execute_with_vector_store(self):
        class FakeVS:
            def delete(self, pks):
                return {"deleted": 2, "errors": None}

        fs = ForgetService()
        plan = fs.preview("\u5fd8\u8bb0\u4e3b\u9898")
        result = fs.execute(plan["confirmation_token"],
                            selected_ids=None, vector_store=FakeVS())
        assert result["success"] is True
