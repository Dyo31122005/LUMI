"""Consultation page: chat, live profile, hypothesis bars and the two result cards."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from ui import components as ui
from ui.landing_sections import PERSONAS

BOT_AVATAR = "🔵"
CUSTOMER_AVATAR = "🙂"

SUGGESTIONS = ["Tôi lo mất việc", "Tôi sắp nghỉ hưu", "Tôi muốn để lại cho gia đình"]
PERSONA_BY_ID = {item["id"]: item for item in PERSONAS}


@st.cache_resource
def knowledge_base() -> KnowledgeBase:
    return KnowledgeBase.load()


@st.cache_data
def field_labels() -> dict[str, str]:
    return {
        item["key"]: item["label_vi"]
        for item in knowledge_base().section("profile_schema")["fields"]
    }


@st.cache_data
def load_recording(persona_id: str) -> dict[str, Any] | None:
    try:
        return Recording.load(persona_id).data
    except FileNotFoundError:
        return None


# --------------------------------------------------------------- start screen


def start_screen() -> None:
    st.title("Xin chào, bạn muốn bắt đầu thế nào?")

    left, right = st.columns(2)
    with left:
        ui.render(st, ui.card(
            "<b>💬 Tự trò chuyện</b>"
            '<div class="lumi-caption" style="margin-top:6px">'
            "Kể về hoàn cảnh của bạn, LUMI sẽ hỏi thêm khi cần.</div>"
        ))
        if st.button("Bắt đầu", type="primary", use_container_width=True):
            st.session_state["lumi_mode"] = "manual"
            st.rerun()
        st.caption("Gợi ý mở đầu:")
        for index, text in enumerate(SUGGESTIONS):
            if st.button(text, key=f"suggest_{index}", use_container_width=True):
                st.session_state["lumi_mode"] = "manual"
                st.session_state["lumi_manual_messages"] = [{"role": "customer", "content": text}]
                st.rerun()

    with right:
        ui.render(st, ui.card(
            "<b>▶ Xem demo với nhân vật mẫu</b>"
            '<div class="lumi-caption" style="margin-top:6px">'
            "Xem lại một phiên LUMI đã tư vấn cho 1 trong 3 nhân vật. Chạy được cả khi không có mạng.</div>"
        ))
        for persona in PERSONAS:
            if st.button(persona["name"], key=f"replay_{persona['id']}", use_container_width=True):
                st.session_state["lumi_mode"] = "replay"
                st.session_state["lumi_persona"] = persona["id"]
                st.rerun()

    st.caption("🔒 Thông tin chỉ dùng cho buổi tư vấn này. Bạn có thể xoá bất kỳ lúc nào.")


# -------------------------------------------------------------------- top bar


def top_bar(title: str, mode_label: str, engine_label: str, persona_css: str) -> None:
    left, middle, right = st.columns([3, 2, 2])
    with left:
        st.html(
            f'<div class="{persona_css}" style="display:flex;align-items:center;gap:10px">'
            f'<span class="lumi-avatar">{ui.esc(title[:1])}</span>'
            f"<b>{ui.esc(title)}</b></div>"
        )
    with middle:
        st.html(
            f'<span class="lumi-demo-badge">{ui.esc(mode_label)}</span> '
            f'<span class="lumi-caption">Engine: {ui.esc(engine_label)}</span>'
        )
    with right:
        columns = st.columns(2)
        with columns[0]:
            senior = st.session_state.get("lumi_senior_mode", False)
            if st.button("Aa Chữ lớn", use_container_width=True, type="secondary" if not senior else "primary"):
                st.session_state["lumi_senior_mode"] = not senior
                st.rerun()
        with columns[1]:
            if st.button("← Trang chủ", use_container_width=True):
                reset_session()
                st.switch_page("pages/landing.py")


def reset_session() -> None:
    for key in ("lumi_mode", "lumi_persona", "lumi_manual_messages", "lumi_step", "lumi_live", "lumi_live_error"):
        st.session_state.pop(key, None)


# ----------------------------------------------------------------- side panel


def profile_panel(data: dict[str, Any]) -> None:
    profile = Profile.model_validate(data["profile"])
    name = profile.name or "bạn"

    st.subheader(f"Hồ sơ của {name}")
    completeness = (data.get("derived") or {}).get("completeness", 0)
    ui.render(st, ui.completeness_bar(completeness))
    ui.render(st, ui.profile_chips(profile, field_labels()))

    insights = data.get("insights") or []
    if insights:
        ui.render(st, "".join(
            f'<div class="lumi-insight"><div class="lumi-eyebrow">💡 LUMI nhận ra</div>{ui.esc(item["reason"])}</div>'
            for item in insights
        ))

    st.subheader("LUMI đang cân nhắc")
    decision = data.get("type_decision") or {}
    turns = data.get("turn_decisions") or []
    probabilities = decision.get("type_probabilities") or (
        turns[-1]["type_probabilities"] if turns else None
    )
    ui.render(st, ui.hypothesis_bars(probabilities, decision.get("confidence")))


# ----------------------------------------------------------------- transcript


def transcript(data: dict[str, Any]) -> None:
    why = data.get("why_ask") or {}
    for index, message in enumerate(data["messages"]):
        role = "assistant" if message["role"] == "assistant" else "user"
        with st.chat_message(role, avatar=BOT_AVATAR if role == "assistant" else CUSTOMER_AVATAR):
            st.markdown(message["content"])
            explanation = why.get(str(index))
            if explanation:
                ui.render(st, ui.why_ask(explanation))


def results(data: dict[str, Any]) -> None:
    decision = data.get("type_decision")
    if not decision:
        st.info("Phiên này chưa đi tới phần đề xuất.")
        return

    type_names = {item["id"]: item["name_vi"] for item in knowledge_base().section("insurance_types")}
    ui.render(st, ui.step_one_card(
        decision,
        data.get("insights") or [],
        type_names.get(decision["insurance_type"], decision["insurance_type"]),
    ))

    ranking = data.get("ranking") or []
    if not ranking:
        st.warning("Không có sản phẩm nào qua được bộ lọc cho hồ sơ này.")
        for item in data.get("excluded") or []:
            st.caption(f"{item['product_name']}: {', '.join(item['reasons'])}")
        return

    profile_name = (data.get("profile") or {}).get("name")
    criteria_names = {
        item["id"]: item["name_vi"] for item in knowledge_base().section("scoring")["criteria"]
    }
    priority = [criteria_names.get(key, key) for key in data.get("priority_criteria", [])]

    ui.render(st, ui.card(
        ui.priority_chips(priority, data.get("weight_reasons", []), profile_name)
        + ui.ranking_cards(ranking, profile_name),
        eyebrow=f"Bước 2 · So sánh{' cho ' + profile_name if profile_name else ''}",
    ))

    ui.render(st, ui.card(ui.heatmap(ranking, data.get("priority_criteria", [])), title="Bản đồ nhiệt 6 tiêu chí"))

    rows = list(knowledge_base().section("comparison_rows")[decision["insurance_type"]])
    priority_rows = _priority_rows(decision["insurance_type"], data.get("priority_criteria", []))
    with st.expander("Bảng chi tiết"):
        ui.render(st, ui.comparison_table(ranking, rows, priority_rows))

    ui.render(st, ui.scenario_card(data.get("scenario")))
    ui.render(st, ui.data_footer())


def _priority_rows(insurance_type: str, priority_criteria: list[str]) -> list[str]:
    mapping = knowledge_base().section("scoring")["criterion_to_rows"][insurance_type]
    rows: list[str] = []
    for criterion in priority_criteria:
        rows.extend(str(item) for item in mapping.get(criterion, ()))
    return rows


# ------------------------------------------------------------------- manual


def live_session() -> tuple[Any, Any] | None:
    """Build the orchestrator for a real conversation, or None if unavailable."""

    if "lumi_live" in st.session_state:
        return st.session_state["lumi_live"]

    try:
        from agents.conversation import ConversationAgent
        from agents.extractor import ProfileExtractor
        from agents.writer import AdvisorWriter
        from core.decision import OpenAIEngine, RuleEngine
        from core.llm import LumiOpenAIClient
        from core.orchestrator import Orchestrator

        kb = knowledge_base()
        client = LumiOpenAIClient()
        prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "decision.md"
        engine: Any = (
            RuleEngine(kb)
            if client.settings.decision_engine == "rule"
            else OpenAIEngine(client, prompt_path.read_text(encoding="utf-8"), kb)
        )
        orchestrator = Orchestrator(
            knowledge_base=kb,
            extractor=ProfileExtractor(client),
            conversation=ConversationAgent(client),
            engine=engine,
            writer=AdvisorWriter(client, kb),
        )
        session = orchestrator.new_session(None, {"assistant_self": "mình", "customer": "bạn", "tone": "thân mật"})
        orchestrator.greeting(session)
        st.session_state["lumi_live"] = (orchestrator, session)
        st.session_state["lumi_engine_label"] = client.settings.decision_engine.title()
        return st.session_state["lumi_live"]
    except Exception as error:  # configuration or connection problem
        st.session_state["lumi_live_error"] = str(error)
        return None


def manual_mode() -> None:
    live = live_session()
    engine_label = st.session_state.get("lumi_engine_label", "—")

    if live is None:
        top_bar("Bạn", "Tự trò chuyện", "Không khả dụng", "persona-mid")
        st.error(
            "LUMI đang gặp sự cố kết nối, nên chưa bắt đầu được phiên tự trò chuyện.",
            icon="⚠",
        )
        st.caption(st.session_state.get("lumi_live_error", ""))
        columns = st.columns(2)
        with columns[0]:
            if st.button("Thử lại", use_container_width=True):
                st.session_state.pop("lumi_live_error", None)
                st.rerun()
        with columns[1]:
            if st.button("Chuyển sang chế độ Phát lại", type="primary", use_container_width=True):
                st.session_state["lumi_mode"] = "replay"
                st.session_state["lumi_persona"] = "mai"
                st.rerun()
        return

    orchestrator, session = live
    top_bar(session.profile.name or "Bạn", "Tự trò chuyện", engine_label, ui.persona_class(session.profile.age))

    # Read the input before drawing anything else: if a later section raises,
    # the visitor can still type instead of being stuck with a broken page.
    prompt = st.chat_input("Nhập câu trả lời của bạn…")
    if prompt:
        try:
            with st.spinner("Đang phân tích hồ sơ…"):
                orchestrator.handle_customer_message(session, prompt)
        except Exception as error:
            st.session_state["lumi_turn_error"] = str(error)
        st.rerun()

    turn_error = st.session_state.pop("lumi_turn_error", None)
    if turn_error:
        st.error("LUMI gặp sự cố khi xử lý câu trả lời vừa rồi. Bạn thử gửi lại nhé.", icon="⚠")
        st.caption(turn_error)

    chat_column, panel_column = st.columns([62, 38], gap="large")

    with chat_column:
        for index, message in enumerate(session.messages):
            role = "assistant" if message.role == "assistant" else "user"
            with st.chat_message(role, avatar=BOT_AVATAR if role == "assistant" else CUSTOMER_AVATAR):
                st.markdown(message.content)
                ui.render(st, ui.why_ask(session.why_ask[index]) if index in session.why_ask else None)

        if session.type_decision:
            st.divider()
            results(live_session_data(session))

    with panel_column:
        st.subheader(f"Hồ sơ của {session.profile.name or 'bạn'}")
        has_profile = bool(session.profile.model_dump(exclude={"provenance"}, exclude_none=True))
        if not has_profile:
            st.caption(
                "Hồ sơ sẽ được điền dần khi bạn trả lời. Mỗi thông tin đều kèm "
                "câu nói gốc của bạn."
            )
        else:
            ui.render(st, ui.completeness_bar((session.derived or {}).get("completeness", 0)))
            ui.render(st, ui.profile_chips(session.profile, field_labels()))
            ui.render(st, ui.insight_cards(session.insights))

        if session.turn_decisions:
            latest = session.turn_decisions[-1]
            st.subheader("LUMI đang cân nhắc")
            ui.render(st, ui.hypothesis_bars(latest.type_probabilities.model_dump(), latest.confidence))

        if has_profile:
            st.divider()
            if st.button("🗑 Xoá hồ sơ", use_container_width=True):
                reset_session()
                st.rerun()


def live_session_data(session: Any) -> dict[str, Any]:
    from core.session_io import session_to_dict

    return session_to_dict(session)


# --------------------------------------------------------------------- entry


mode = st.session_state.get("lumi_mode")

if mode is None:
    start_screen()
elif mode == "manual":
    manual_mode()
else:
    persona_id = st.session_state.get("lumi_persona", "mai")
    data = load_recording(persona_id)
    if data is None:
        st.warning(f"Chưa có phiên đã ghi cho {persona_id}. Chạy `scripts/run_cli.py` để tạo.")
        if st.button("Quay lại"):
            reset_session()
            st.rerun()
    else:
        persona = PERSONA_BY_ID.get(persona_id, {})
        profile_age = (data.get("profile") or {}).get("age")
        if profile_age and profile_age >= 55:
            st.session_state.setdefault("lumi_senior_mode", True)

        top_bar(
            persona.get("name", persona_id),
            "Demo · Phát lại",
            "Phát lại",
            ui.persona_class(profile_age),
        )

        chat_column, panel_column = st.columns([62, 38], gap="large")
        with chat_column:
            st.subheader("Hội thoại")
            transcript(data)
            st.divider()
            results(data)
        with panel_column:
            profile_panel(data)
            st.divider()
            if st.button("↺ Chọn nhân vật khác", use_container_width=True):
                reset_session()
                st.rerun()
