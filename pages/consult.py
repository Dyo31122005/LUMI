"""Consultation page: chat, live profile, hypothesis bars and the two result cards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st

from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from ui import components as ui
from ui.landing_sections import PERSONAS

BOT_AVATAR = str(ui.MASCOT_PATH)
CUSTOMER_AVATAR = ":material/person:"

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
    st.html(ui.page_intro(
        "Tư vấn cho hoàn cảnh của bạn",
        "Hãy bắt đầu từ điều bạn đang quan tâm nhất",
        "Bạn không cần biết tên sản phẩm hay thuật ngữ bảo hiểm. LUMI sẽ hỏi từng bước và giải thích vì sao cần thông tin đó.",
    ))

    with st.container(key="lumi_primary_start"):
        intro, mascot = st.columns([1.45, 0.55], gap="large", vertical_alignment="center")
        with intro:
            st.html(
                '<div class="lumi-start-card">'
                f'{ui.material_icon("forum")}<h2>Bắt đầu một phiên tư vấn mới</h2>'
                '<p>Cuộc trò chuyện thường mất khoảng 3–5 phút. Hồ sơ được tạo dần ngay bên cạnh và có thể xoá bất kỳ lúc nào.</p>'
                '</div>'
            )
            if st.button(
                "Bắt đầu trò chuyện",
                type="primary",
                icon=":material/arrow_forward:",
                use_container_width=True,
            ):
                st.session_state["lumi_mode"] = "manual"
                st.rerun()
        with mascot:
            st.image(str(ui.MASCOT_PATH), caption="Mascot LUMI", use_container_width=True)

    st.markdown("#### Hoặc chọn một câu để bắt đầu nhanh")
    suggestions = st.columns(len(SUGGESTIONS))
    for index, (column, text) in enumerate(zip(suggestions, SUGGESTIONS)):
        with column:
            if st.button(text, key=f"suggest_{index}", use_container_width=True):
                st.session_state["lumi_mode"] = "manual"
                st.session_state["lumi_pending_prompt"] = text
                st.rerun()

    st.html(
        '<div class="lumi-security-note">'
        f'{ui.material_icon("lock")} Thông tin chỉ dùng cho buổi tư vấn này. Bạn có thể xoá bất kỳ lúc nào.'
        '</div>'
    )

    st.divider()
    st.html(ui.page_intro(
        "Muốn xem trước?",
        "Khám phá một hành trình mẫu",
        "Các phiên phát lại chạy từ dữ liệu đã ghi và giúp bạn xem trọn quy trình trước khi chia sẻ thông tin của mình.",
    ))
    columns = st.columns(3, gap="medium")
    for column, persona in zip(columns, PERSONAS):
        with column:
            st.html(
                f'<div class="lumi-persona-card {persona["css"]}">'
                f'<span class="lumi-avatar">{ui.esc(persona["initial"])}</span>'
                f'<h3>{ui.esc(persona["name"])}</h3>'
                f'<p class="lumi-muted">{ui.esc(persona["situation"])}</p>'
                f'<span class="lumi-tag lumi-tag-note">{ui.esc(persona["recommendation"])}</span>'
                '</div>'
            )
            if st.button(
                f"Xem hành trình {persona['name'].split(',')[0]}",
                key=f"replay_{persona['id']}",
                icon=":material/play_circle:",
                use_container_width=True,
            ):
                st.session_state["lumi_mode"] = "replay"
                st.session_state["lumi_persona"] = persona["id"]
                st.rerun()


# -------------------------------------------------------------------- top bar


def top_bar(title: str, mode_label: str, engine_label: str, persona_css: str) -> None:
    with st.container(key="lumi_session_toolbar"):
        left, middle, right = st.columns([3.2, 2.1, 2.4], vertical_alignment="center")
        with left:
            st.html(
                f'<div class="lumi-session-head {persona_css}">'
                f'<span class="lumi-avatar">{ui.esc(title[:1])}</span>'
                f'<div><h2>{ui.esc(title)}</h2><p>Phiên tư vấn cá nhân hoá</p></div></div>'
            )
        with middle:
            st.html(
                f'<span class="lumi-status-badge">{ui.material_icon("radio_button_checked")} {ui.esc(mode_label)}</span> '
                f'<span class="lumi-caption">Engine: {ui.esc(engine_label)}</span>'
            )
        with right:
            columns = st.columns(2)
            with columns[0]:
                senior = st.session_state.get("lumi_senior_mode", False)
                if st.button(
                    "Chữ lớn",
                    icon=":material/text_increase:",
                    use_container_width=True,
                    type="secondary" if not senior else "primary",
                ):
                    st.session_state["lumi_senior_mode"] = not senior
                    st.rerun()
            with columns[1]:
                if st.button("Bắt đầu lại", icon=":material/restart_alt:", use_container_width=True):
                    reset_session()
                    st.rerun()


def reset_session() -> None:
    for key in (
        "lumi_mode", "lumi_persona", "lumi_manual_messages", "lumi_pending_prompt",
        "lumi_step", "lumi_live", "lumi_live_error", "lumi_turn_error",
        "lumi_speech", "lumi_draft", "lumi_last_clip", "lumi_voice_error",
        "lumi_audio_cache", "lumi_play", "lumi_play_armed", "lumi_autoplayed",
    ):
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
            '<div class="lumi-insight"><div class="lumi-eyebrow">'
            f'{ui.material_icon("lightbulb")} LUMI nhận ra</div>{ui.esc(item["reason"])}</div>'
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
            icon=":material/error:",
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

    pending_prompt = st.session_state.pop("lumi_pending_prompt", None)
    if pending_prompt:
        try:
            with st.spinner("Đang phân tích điều bạn quan tâm…"):
                orchestrator.handle_customer_message(session, pending_prompt)
        except Exception as error:
            st.session_state["lumi_turn_error"] = str(error)
        st.rerun()

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
        st.error("LUMI gặp sự cố khi xử lý câu trả lời vừa rồi. Bạn thử gửi lại nhé.", icon=":material/error:")
        st.caption(turn_error)

    chat_column, panel_column = st.columns([62, 38], gap="large")

    arm_autoplay_for_large_text(session)

    with chat_column:
        st.html(
            '<div class="lumi-chat-heading"><div><div class="lumi-eyebrow">Cuộc trò chuyện</div>'
            '<h2>LUMI đang tìm hiểu hoàn cảnh của bạn</h2></div>'
            '<span class="lumi-status-badge">Đang tư vấn</span></div>'
        )
        with st.container(key="lumi_chat_panel"):
            for index, message in enumerate(session.messages):
                role = "assistant" if message.role == "assistant" else "user"
                with st.chat_message(role, avatar=BOT_AVATAR if role == "assistant" else CUSTOMER_AVATAR):
                    st.markdown(message.content)
                    ui.render(st, ui.why_ask(session.why_ask[index]) if index in session.why_ask else None)
                    if role == "assistant":
                        play_controls(index, message.content, session.profile.age)

            if session.type_decision:
                st.divider()
                results(live_session_data(session))

        voice_input()

    with panel_column:
        with st.container(height=720, border=False, key="lumi_profile_panel"):
            st.subheader(f"Hồ sơ của {session.profile.name or 'bạn'}")
            st.caption("Được cập nhật trực tiếp từ cuộc trò chuyện")
            has_profile = bool(session.profile.model_dump(exclude={"provenance"}, exclude_none=True))
            if not has_profile:
                st.info(
                    "Hồ sơ sẽ được điền dần khi bạn trả lời. Mỗi thông tin đều kèm câu nói gốc của bạn.",
                    icon=":material/manage_accounts:",
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
                if st.button("Xoá hồ sơ", icon=":material/delete:", use_container_width=True):
                    reset_session()
                    st.rerun()


def live_session_data(session: Any) -> dict[str, Any]:
    from core.session_io import session_to_dict

    return session_to_dict(session)


# --------------------------------------------------------------------- voice


@st.cache_data(show_spinner=False)
def _speech_hint() -> str:
    from core.speech import transcription_prompt

    return transcription_prompt(knowledge_base())


def speech_client() -> Any | None:
    """The speech client, or None when voice is off or unavailable."""

    if "lumi_speech" in st.session_state:
        return st.session_state["lumi_speech"]

    client: Any | None
    try:
        from core.speech import SpeechClient

        client = SpeechClient()
        if not client.enabled:
            client = None
    except Exception:
        # Voice is a second way in, never a requirement. Typing still works.
        client = None
    st.session_state["lumi_speech"] = client
    return client


def speak_message(text: str, age: int | None) -> bytes | None:
    """Synthesise a reply, reusing audio already produced this session.

    Synthesis happens on request, never for every message on every rerun:
    a ten-message transcript would otherwise cost ten calls each time the
    page redraws.
    """

    client = speech_client()
    if client is None:
        return None

    from core.speech import style_for_age

    style = style_for_age(age)
    cache: dict[str, bytes] = st.session_state.setdefault("lumi_audio_cache", {})
    key = hashlib.sha1(f"{style.voice}|{text}".encode("utf-8")).hexdigest()

    if key not in cache:
        try:
            with st.spinner("Đang chuẩn bị giọng đọc…"):
                cache[key] = client.speak(text, style)
        except Exception as error:
            st.session_state["lumi_voice_error"] = str(error)
            return None
    return cache[key]


def play_controls(index: int, text: str, age: int | None) -> None:
    """A listen button per reply, plus the player once it has been asked for."""

    if speech_client() is None:
        return

    if st.session_state.get("lumi_play") != index:
        if st.button("Nghe", key=f"lumi_play_{index}", icon=":material/volume_up:"):
            st.session_state["lumi_play"] = index
            st.session_state["lumi_play_armed"] = True
            st.rerun()
        return

    audio = speak_message(text, age)
    if audio is None:
        return
    # Autoplay only on the run that asked for it, so redraws do not restart it.
    armed = bool(st.session_state.pop("lumi_play_armed", False))
    st.audio(audio, format="audio/mp3", autoplay=armed)


def arm_autoplay_for_large_text(session: Any) -> None:
    """Large-text mode reads the newest reply aloud on its own (VOICE-08).

    Customers who turned on large text are the ones least served by reading a
    screen, so the reply plays without them hunting for a button.
    """

    if not st.session_state.get("lumi_senior_mode") or speech_client() is None:
        return
    last = len(session.messages) - 1
    if last < 0 or session.messages[last].role != "assistant":
        return
    if st.session_state.get("lumi_autoplayed") == last:
        return
    st.session_state["lumi_autoplayed"] = last
    st.session_state["lumi_play"] = last
    st.session_state["lumi_play_armed"] = True


def voice_input() -> None:
    """Record, transcribe, then let the customer check the text before sending.

    The transcript is never sent straight through: a misheard amount would
    flow into the advice, and showing it is the cheapest way to stop that.
    """

    client = speech_client()
    if client is None:
        return

    recording = st.audio_input("Hoặc nói với LUMI", key="lumi_mic")
    if recording is not None:
        data = recording.getvalue()
        # Streamlit hands back the same recording on every rerun, so remember
        # which clip has already been transcribed.
        fingerprint = hashlib.sha1(data).hexdigest()
        if fingerprint != st.session_state.get("lumi_last_clip"):
            st.session_state["lumi_last_clip"] = fingerprint
            st.session_state.pop("lumi_voice_error", None)
            try:
                with st.spinner("Đang nghe bạn nói…"):
                    st.session_state["lumi_draft"] = client.transcribe(
                        data,
                        filename=getattr(recording, "name", None) or "speech.wav",
                        prompt=_speech_hint(),
                    )
            except Exception as error:
                st.session_state["lumi_voice_error"] = str(error)
            st.rerun()

    error = st.session_state.get("lumi_voice_error")
    if error:
        st.warning(f"{error} Bạn ghi lại hoặc gõ vào ô bên dưới nhé.", icon=":material/mic_off:")

    draft = st.session_state.get("lumi_draft")
    if not draft:
        return

    st.caption("LUMI nghe được thế này. Bạn sửa lại nếu chưa đúng rồi hãy gửi.")
    edited = st.text_area("Nội dung sẽ gửi", value=draft, key="lumi_draft_text", height=100)
    send, discard = st.columns(2)
    with send:
        if st.button("Gửi", type="primary", icon=":material/send:", use_container_width=True):
            text = (edited or "").strip()
            st.session_state.pop("lumi_draft", None)
            if text:
                st.session_state["lumi_pending_prompt"] = text
            st.rerun()
    with discard:
        if st.button("Bỏ, ghi lại", icon=":material/close:", use_container_width=True):
            st.session_state.pop("lumi_draft", None)
            st.rerun()


# --------------------------------------------------------------------- entry


mode = st.session_state.get("lumi_mode")
ui.app_header(
    st,
    "consult",
    report_ready=mode == "replay" and bool(st.session_state.get("lumi_persona")),
)

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
            st.html(
                '<div class="lumi-chat-heading"><div><div class="lumi-eyebrow">Phiên mẫu đã hoàn thành</div>'
                f'<h2>Hành trình của {ui.esc(persona.get("name", persona_id))}</h2></div>'
                '<span class="lumi-status-badge">Phát lại</span></div>'
            )
            with st.container(key="lumi_chat_panel"):
                transcript(data)
                st.divider()
                results(data)
        with panel_column:
            with st.container(height=720, border=False, key="lumi_profile_panel"):
                profile_panel(data)
                st.divider()
                if st.button("Chọn nhân vật khác", icon=":material/switch_account:", use_container_width=True):
                    reset_session()
                    st.rerun()

        st.divider()
        st.html(ui.page_intro(
            "Tiếp tục khám phá",
            "Bạn muốn làm gì tiếp theo?",
            "Xem báo cáo cô đọng, đối chiếu ba hành trình hoặc bắt đầu phiên dành cho chính bạn.",
        ))
        actions = st.columns(3)
        with actions[0]:
            ui.page_link(st, "pages/report.py", label="Xem báo cáo", icon=":material/description:")
        with actions[1]:
            ui.page_link(st, "pages/journeys.py", label="So sánh 3 hành trình", icon=":material/route:")
        with actions[2]:
            if st.button("Tư vấn cho tôi", type="primary", icon=":material/forum:", use_container_width=True):
                reset_session()
                st.session_state["lumi_mode"] = "manual"
                st.rerun()
