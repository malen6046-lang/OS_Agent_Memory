"""System health dashboard."""

import streamlit as st

from src.components.common import perform_api_call, render_api_result


st.title("系统状态")
st.caption("检查 FastAPI 及其依赖状态。")

if st.button("刷新系统状态", type="primary"):
    st.session_state.last_health_result = perform_api_call(
        "健康检查",
        lambda client: client.health(),
    )

result = st.session_state.last_health_result
if result is None:
    st.info("点击按钮开始检查；前端仅调用 FastAPI。")
else:
    render_api_result(
        result,
        success_message="系统健康检查通过",
        show_payload=False,
    )
    if result.success and isinstance(result.data, dict):
        status_column, mode_column, service_column = st.columns(3)
        status_column.metric("服务状态", result.data.get("status", "unknown"))
        mode_column.metric(
            "后端模式",
            "Mock" if result.data.get("mock") else "Real",
        )
        service_column.metric(
            "服务名称",
            result.data.get("service", "os-agent-memory"),
        )

        st.subheader("依赖状态")
        embedding, vector = st.columns(2)
        with embedding:
            st.markdown("#### Embedding")
            st.json(result.data.get("embedding", {}))
        with vector:
            st.markdown("#### Vector Store")
            st.json(result.data.get("vector_store", {}))

        with st.expander("查看完整健康响应"):
            st.json(result.data)
