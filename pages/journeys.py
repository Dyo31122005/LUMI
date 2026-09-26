"""Three journeys side by side (lumi-ui-design.md §6.2)."""

from __future__ import annotations

import streamlit as st

from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from ui import components as ui
from ui.landing_sections import PERSONAS

st.title("Cùng LUMI, ba hành trình khác nhau")
st.caption("Lời chào giống hệt nhau. Từ câu thứ hai, mọi thứ bắt đầu khác đi.")

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
st.html(ui.card(
    f'<div class="lumi-eyebrow">Lời chào — giống nhau cho cả ba</div>'
    f'<div class="lumi-muted">{ui.esc(opening)}</div>'
))

columns = st.columns(len(loaded))
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
            f'<div class="lumi-persona-card {persona["css"]}">'
            f'<span class="lumi-avatar">{ui.esc(persona["initial"])}</span>'
            f'<div style="margin-top:10px"><b>{ui.esc(persona["name"])}</b></div>'
            f'<div class="lumi-caption">{ui.esc(profile.occupation or persona["situation"])}</div>'
            "</div>"
        )

        st.markdown("**Câu hỏi riêng**")
        for question in questions[:3]:
            st.caption(f"• {question}")

        st.markdown("**LUMI nhận ra**")
        st.html(ui.insight_cards(data.get("insights") or []) or '<span class="lumi-caption">—</span>')

        st.markdown("**Loại đề xuất**")
        st.html(f'<span class="lumi-tag lumi-tag-note">{ui.esc(type_names.get(decision.get("insurance_type"), "—"))}</span>')

        st.markdown("**Điều quan trọng nhất**")
        st.html("".join(f'<span class="lumi-chip"><b>{ui.esc(item)}</b></span>' for item in priority) or "—")

        st.markdown("**Sản phẩm đầu bảng**")
        st.write(ranking[0]["product_name"] if ranking else "—")

        if st.button("Xem lại hành trình", key=f"open_{persona['id']}", use_container_width=True):
            st.session_state["lumi_mode"] = "replay"
            st.session_state["lumi_persona"] = persona["id"]
            st.switch_page("pages/consult.py")

st.html(ui.data_footer())
