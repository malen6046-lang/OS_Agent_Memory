"""Memory ingestion form."""

from datetime import datetime, timezone
import json

import streamlit as st

from src.components.common import (
    new_event_id,
    new_idempotency_key,
    new_request_id,
    perform_api_call,
    remember_memory_ids,
    render_api_result,
)


st.title("记忆导入")
st.caption("构造 V1.2 Envelope，并通过 POST /api/v1/events/ingest 写入。")

with st.form("ingest_form"):
    user_id = st.text_input("用户 ID *", value=st.session_state.active_user_id)
    content = st.text_area(
        "记忆内容 *",
        placeholder="例如：发布前需要检查测试结果、版本号和回滚方案。",
        height=140,
    )
    scene, source = st.columns(2)
    with scene:
        scene_value = st.text_input("场景 *", value="mvp_demo")
    with source:
        source_value = st.selectbox(
            "来源 *",
            ["tool_result", "user_behavior", "manual_config", "cross_scene"],
        )

    with st.expander("高级字段"):
        session_id = st.text_input("会话 ID（可选）")
        source_event_id = st.text_input(
            "来源事件 ID",
            placeholder="留空时自动生成",
        )
        idempotency_key = st.text_input(
            "幂等键",
            placeholder="留空时自动生成",
        )
        extra_payload = st.text_area(
            "附加 payload JSON",
            value="{}",
            help="必须是 JSON 对象；content 字段由上方记忆内容覆盖。",
        )

    submitted = st.form_submit_button("导入记忆", type="primary")

if submitted:
    if not user_id.strip() or not content.strip() or not scene_value.strip():
        st.error("用户 ID、记忆内容和场景不能为空。")
    else:
        try:
            payload_extra = json.loads(extra_payload)
            if not isinstance(payload_extra, dict):
                raise ValueError("附加 payload 必须是 JSON 对象")
        except (json.JSONDecodeError, ValueError) as exc:
            st.error(f"附加 payload JSON 无效：{exc}")
        else:
            request_id = new_request_id()
            event_id = source_event_id.strip() or new_event_id()
            payload_extra["content"] = content.strip()
            envelope = {
                "contract_version": "1.0",
                "request_id": request_id,
                "idempotency_key": (
                    idempotency_key.strip() or new_idempotency_key()
                ),
                "user_id": user_id.strip(),
                "session_id": session_id.strip() or None,
                "scene": scene_value.strip(),
                "source": source_value,
                "source_event_id": event_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload_extra,
            }
            st.session_state.active_user_id = user_id.strip()
            st.session_state.last_ingest_result = perform_api_call(
                "记忆导入",
                lambda client: client.ingest(
                    envelope,
                    request_id=request_id,
                ),
            )

result = st.session_state.last_ingest_result
if result is not None:
    if render_api_result(result, success_message="记忆导入成功"):
        data = result.data if isinstance(result.data, dict) else {}
        workflow = data.get("result", {})
        repository = (
            workflow.get("repository_result", {})
            if isinstance(workflow, dict)
            else {}
        )
        records = repository.get("records", []) if isinstance(repository, dict) else []
        memory_ids = [
            record.get("memory_id")
            for record in records
            if isinstance(record, dict) and record.get("memory_id")
        ]
        remember_memory_ids(memory_ids)
        if memory_ids:
            st.write("生成的 memory_id：")
            for memory_id in memory_ids:
                st.code(memory_id)
