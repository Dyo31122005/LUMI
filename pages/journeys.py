"""Compare the three recorded LUMI journeys."""

from __future__ import annotations

import streamlit as st

from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from ui import components as ui
from ui.landing_sections import PERSONAS

ui.app_header(st, "journeys", report_ready=bool(st.session_state.get("lumi_persona")))
st.html(ui.page_intro(
    "Ba hoàn cảnh · ba hướng tư vấn",
    "Cùng LUMI, ba hành trình khác nhau",
    "Lời chào giống nhau, nhưng câu hỏi, nhận định và kết quả thay đổi theo điều mỗi người thực sự cần.",
))

kb = KnowledgeBase.load()
type_names = {item["id"]: item["name_vi"] for item in kb.section("insurance_types")}
criteria_names = {item["id"]: item["name_vi"] for item in kb.section("scoring")["criteria"]}

loaded: list[tuple[dict[str, str], dict]] = []
for persona in PERSONAS:
    try:
        loaded.append((persona, Recording.load(persona["id"]).data))
    except FileNotFoundError:
        continue

if not loaded:
    st.warning("Chưa có phiên đã ghi nào. Chạy `scripts/run_cli.py` để tạo.")
    st.stop()

opening = loaded[0][1]["messages"][0]["content"]
ui.render(st, ui.card(
    f'<div class="lumi-eyebrow">Điểm xuất phát chung</div>'
    f'<div class="lumi-muted">{ui.esc(opening)}</div>',
    title="Một lời chào, nhiều hướng đi",
))

columns = st.columns(len(loaded), gap="medium")
for column, (persona, data) in zip(columns, loaded):
    with column:
        profile = Profile.model_validate(data["profile"])
        decision = data.get("type_decision") or {}
        ranking = data.get("ranking") or []
        questions = [
            message["content"]
            for message in data["messages"][1:]
            if message["role"] == "assistant" and message["content"].rstrip().endswith("?")
        ]
        priority = [criteria_names.get(key, key) for key in data.get("priority_criteria", [])]

        st.html(
            f'<article class="lumi-persona-card lumi-journey-card {persona["css"]}">'
            '<div class="lumi-persona-head">'
            f'<span class="lumi-avatar">{ui.esc(persona["initial"])}</span>'
            f'<div><h3>{ui.esc(persona["name"])}</h3>'
            f'<p>{ui.esc(profile.occupation or persona["situation"])}</p></div></div>'
            '<div class="lumi-journey-result">'
            f'<small>Đề xuất</small><strong>{ui.esc(type_names.get(decision.get("insurance_type"), "—"))}</strong>'
            '</div></article>'
        )

        st.markdown("##### Câu hỏi riêng")
        for question in questions[:3]:
            st.caption(f"• {question}")

        st.markdown("##### LUMI nhận ra")
        ui.render(st, ui.insight_cards(data.get("insights") or []) or '<span class="lumi-caption">Chưa có nhận định.</span>')

        st.markdown("##### Điều quan trọng nhất")
        ui.render(st, "".join(f'<span class="lumi-chip"><b>{ui.esc(item)}</b></span>' for item in priority) or "—")

        st.markdown("##### Sản phẩm đầu bảng")
        st.write(ranking[0]["product_name"] if ranking else "—")

        if st.button(
            f"Xem hành trình {persona['name'].split(',')[0]}",
            key=f"open_{persona['id']}",
            icon=":material/play_circle:",
            use_container_width=True,
        ):
            st.session_state["lumi_mode"] = "replay"
            st.session_state["lumi_persona"] = persona["id"]
            st.switch_page("pages/consult.py")

st.divider()
with st.container(key="lumi_journey_cta"):
    copy, action = st.columns([2.4, 1], vertical_alignment="center")
    with copy:
        st.subheader("Câu chuyện của bạn sẽ tạo nên một hành trình khác")
        st.caption("Bắt đầu từ điều bạn đang lo; LUMI sẽ hỏi thêm từng bước.")
    with action:
        if st.button("Tư vấn cho tôi", type="primary", icon=":material/forum:", use_container_width=True):
            st.session_state["lumi_mode"] = "manual"
            st.session_state.pop("lumi_persona", None)
            st.switch_page("pages/consult.py")

ui.render(st, ui.data_footer())
