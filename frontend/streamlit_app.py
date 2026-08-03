"""Entrypoint and shared frame for the OS Agent Memory MVP interface."""

import streamlit as st

from src.components.common import (
    initialize_session,
    perform_api_call,
    render_request_history,
)


st.set_page_config(
    page_title="OS Agent Memory MVP",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)
initialize_session()

pages = {
    "系统": [
        st.Page(
            "src/pages/status.py",
            title="系统状态",
            icon="🩺",
            default=True,
        )
    ],
    "记忆操作": [
        st.Page("src/pages/ingest.py", title="记忆导入", icon="📥"),
        st.Page("src/pages/search.py", title="记忆搜索", icon="🔎"),
        st.Page("src/pages/forget.py", title="记忆遗忘", icon="🗑️"),
    ],
}
navigation = st.navigation(pages)

with st.sidebar:
    st.divider()
    st.subheader("连接设置")
    st.text_input(
        "FastAPI 地址",
        key="api_base_url",
        help="必须包含 API 版本前缀，例如 http://127.0.0.1:8000/api/v1",
    )
    st.number_input(
        "请求超时（秒）",
        min_value=0.5,
        max_value=60.0,
        step=0.5,
        key="api_timeout_seconds",
    )
    if st.button("测试连接", use_container_width=True):
        result = perform_api_call("健康检查", lambda client: client.health())
        if result is not None:
            if result.success:
                st.success("FastAPI 连接正常")
            else:
                st.error("FastAPI 已响应，但健康检查失败")
            st.caption(f"request_id：`{result.request_id}`")
            if result.meta.degraded:
                st.warning("后端当前处于 degraded 模式")

    st.divider()
    st.subheader("最近请求")
    render_request_history()

navigation.run()
