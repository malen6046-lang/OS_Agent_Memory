from app.core.responses import success_response


def test_orchestrator_meta_is_promoted_to_http_envelope():
    payload = {
        "value": "ok",
        "__response_meta": {
            "elapsed_ms": 123,
            "degraded": False,
            "provider": "kylin-ai-runtime",
        },
    }

    response = success_response("req_timing", payload)

    assert response.meta.elapsed_ms == 123
    assert response.meta.provider == "kylin-ai-runtime"
    assert response.data == {"value": "ok"}


def test_response_without_orchestrator_meta_keeps_default_meta():
    response = success_response("req_default", {"value": "ok"})

    assert response.meta.elapsed_ms == 0
    assert response.data == {"value": "ok"}
