"""User-scoped memory search page."""

import json

import streamlit as st

from src.components.common import (
    new_request_id,
    perform_api_call,
    remember_memory_ids,
    render_api_result,
)


st.title("记忆搜索")
st.caption("调用 POST /api/v1/memory/search；后端负责 user_id 和 status 隔离。")

with st.form("search_form"):
    user_id = st.text_input("用户 ID *", value=st.session_state.active_user_id)
    query = st.text_input(
        "搜索内容 *",
        placeholder="例如：发布检查清单",
    )
    top_k = st.slider("返回数量", min_value=1, max_value=20, value=5)
    with st.expander("过滤条件"):
        filters_text = st.text_area("filters JSON", value="{}")
    submitted = st.form_submit_button("搜索记忆", type="primary")

if submitted:
    if not user_id.strip() or not query.strip():
        st.error("用户 ID 和搜索内容不能为空。")
    else:
        try:
            filters = json.loads(filters_text)
            if not isinstance(filters, dict):
                raise ValueError("filters 必须是 JSON 对象")
        except (json.JSONDecodeError, ValueError) as exc:
            st.error(f"filters JSON 无效：{exc}")
        else:
            request_id = new_request_id()
            st.session_state.active_user_id = user_id.strip()
            st.session_state.last_search_result = perform_api_call(
                "记忆搜索",
                lambda client: client.search(
                    {
                        "user_id": user_id.strip(),
                        "query": query.strip(),
                        "top_k": top_k,
                        "filters": filters,
                    },
                    request_id=request_id,
                ),
            )

result = st.session_state.last_search_result
if result is not None:
    if render_api_result(result, success_message="搜索完成", show_payload=False):
        data = result.data if isinstance(result.data, dict) else {}
        items = data.get("items", []) if isinstance(data.get("items", []), list) else []
        memory_ids = [
            item.get("memory_id")
            for item in items
            if isinstance(item, dict) and item.get("memory_id")
        ]
        st.session_state.search_memory_ids = memory_ids
        remember_memory_ids(memory_ids)

        if not items:
            st.info("没有找到符合条件的有效记忆。")
        else:
            st.subheader(f"搜索结果（{len(items)}）")
            display_rows = [
                {
                    "memory_id": item.get("memory_id"),
                    "内容": item.get("content_text", ""),
                    "状态": item.get("status", ""),
                    "分数": round(float(item.get("score", 0.0)), 4),
                }
                for item in items
                if isinstance(item, dict)
            ]
            st.dataframe(
                display_rows,
                use_container_width=True,
                hide_index=True,
            )
            with st.expander("查看原始搜索结果"):
                st.json(items)
