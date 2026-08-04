"""Two-stage memory forget page."""

import streamlit as st

from src.components.common import (
    forget_memory_ids,
    new_request_id,
    perform_api_call,
    render_api_result,
)


st.title("记忆遗忘")
st.caption("先预览候选项和确认令牌，再执行 tombstone 与精确向量删除。")

known_ids = list(
    dict.fromkeys(
        [
            *st.session_state.search_memory_ids,
            *st.session_state.known_memory_ids,
        ]
    )
)

with st.form("forget_preview_form"):
    user_id = st.text_input("用户 ID *", value=st.session_state.active_user_id)
    selected_known = st.multiselect(
        "选择当前会话中的 memory_id",
        options=known_ids,
        default=st.session_state.search_memory_ids,
    )
    manual_ids = st.text_area(
        "其他 memory_id",
        placeholder="每行一个，或使用英文逗号分隔",
    )
    reason = st.text_input("遗忘原因（可选）", value="用户主动请求")
    preview_submitted = st.form_submit_button("生成遗忘预览", type="primary")

if preview_submitted:
    parsed_manual = [
        item.strip()
        for line in manual_ids.splitlines()
        for item in line.split(",")
        if item.strip()
    ]
    memory_ids = list(dict.fromkeys([*selected_known, *parsed_manual]))
    if not user_id.strip() or not memory_ids:
        st.error("用户 ID 不能为空，并且至少选择一个 memory_id。")
    else:
        request_id = new_request_id()
        st.session_state.active_user_id = user_id.strip()
        result = perform_api_call(
            "遗忘预览",
            lambda client: client.preview_forget(
                {
                    "user_id": user_id.strip(),
                    "memory_ids": memory_ids,
                    "reason": reason.strip() or None,
                },
                request_id=request_id,
            ),
        )
        st.session_state.last_preview_result = result
        if result is not None and result.success and isinstance(result.data, dict):
            st.session_state.forget_plan = result.data

preview_result = st.session_state.last_preview_result
if preview_result is not None:
    render_api_result(
        preview_result,
        success_message="遗忘预览已生成，请核对后确认",
    )

plan = st.session_state.forget_plan
if isinstance(plan, dict):
    st.divider()
    st.subheader("确认遗忘")
    affected_ids = [
        item
        for item in plan.get("affected_memory_ids", [])
        if isinstance(item, str) and item
    ]
    st.write("即将遗忘：")
    for memory_id in affected_ids:
        st.code(memory_id)
    st.caption(f"plan_id：`{plan.get('plan_id', '')}`")

    with st.form("forget_execute_form"):
        execute_ids = st.multiselect(
            "最终确认的 memory_id *",
            options=affected_ids,
            default=affected_ids,
        )
        confirmed = st.checkbox(
            "我确认执行逻辑删除和精确向量删除",
        )
        execute_submitted = st.form_submit_button(
            "确认执行遗忘",
            type="primary",
        )

    if execute_submitted:
        if not confirmed or not execute_ids:
            st.error("请勾选确认，并至少保留一个 memory_id。")
        else:
            request_id = new_request_id()
            result = perform_api_call(
                "执行遗忘",
                lambda client: client.execute_forget(
                    {
                        "user_id": plan.get("user_id"),
                        "plan_id": plan.get("plan_id"),
                        "confirmation_token": plan.get("confirmation_token"),
                        "selected_ids": execute_ids,
                    },
                    request_id=request_id,
                ),
            )
            st.session_state.last_execute_result = result
            if result is not None and result.success:
                forget_memory_ids(execute_ids)
                st.session_state.forget_plan = None

execute_result = st.session_state.last_execute_result
if execute_result is not None:
    st.divider()
    render_api_result(
        execute_result,
        success_message="记忆遗忘执行成功",
    )
