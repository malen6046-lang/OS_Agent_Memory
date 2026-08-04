from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def test_streamlit_entrypoint_renders_without_backend_connection():
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"

    app = AppTest.from_file(str(app_path), default_timeout=10).run()

    assert not app.exception
    assert any(
        heading.value == "连接设置" for heading in app.sidebar.subheader
    )


@pytest.mark.parametrize(
    ("page_name", "expected_title"),
    [
        ("status.py", "系统状态"),
        ("ingest.py", "记忆导入"),
        ("search.py", "记忆搜索"),
        ("forget.py", "记忆遗忘"),
    ],
)
def test_each_page_renders_with_shared_session_state(
    page_name,
    expected_title,
):
    page_path = (
        Path(__file__).resolve().parents[1] / "src" / "pages" / page_name
    )
    app = AppTest.from_file(str(page_path), default_timeout=10)
    defaults = {
        "api_base_url": "http://127.0.0.1:8000/api/v1",
        "api_timeout_seconds": 1.0,
        "active_user_id": "usr_demo",
        "request_history": [],
        "known_memory_ids": [],
        "search_memory_ids": [],
        "last_health_result": None,
        "last_ingest_result": None,
        "last_search_result": None,
        "last_preview_result": None,
        "last_execute_result": None,
        "forget_plan": None,
    }
    for key, value in defaults.items():
        app.session_state[key] = value

    app.run()

    assert not app.exception
    assert any(title.value == expected_title for title in app.title)
