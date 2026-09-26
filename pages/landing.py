"""Landing page (lumi-ui-design.md §4)."""

from __future__ import annotations

import streamlit as st

from ui import landing_sections as sections
from ui.components import card, esc

st.html(sections.hero())

start, demo = st.columns([1, 1])
with start:
    if st.button("Bắt đầu trò chuyện", type="primary", use_container_width=True):
        st.session_state["lumi_mode"] = "manual"
        st.session_state.pop("lumi_persona", None)
        st.switch_page("pages/consult.py")
with demo:
    if st.button("Xem demo 3 phút", use_container_width=True):
        st.session_state["lumi_mode"] = "replay"
        st.session_state["lumi_persona"] = "mai"
        st.switch_page("pages/consult.py")

st.html(sections.commitments())

st.subheader("Cách hoạt động")
st.html(sections.how_it_works())

st.subheader("Cùng một lời chào, ba hành trình khác nhau")
st.caption("Bấm một nhân vật để xem LUMI tư vấn cho hoàn cảnh đó.")

columns = st.columns(3)
for column, persona in zip(columns, sections.PERSONAS):
    with column:
        st.html(sections.persona_card(persona))
        if st.button(f"Xem hành trình của {persona['name']}", key=f"go_{persona['id']}", use_container_width=True):
            st.session_state["lumi_mode"] = "replay"
            st.session_state["lumi_persona"] = persona["id"]
            st.switch_page("pages/consult.py")

st.caption("Nhân vật và sản phẩm trong demo là hư cấu.")

st.subheader("Phía sau LUMI")
st.html(sections.behind())

st.subheader("Câu hỏi thường gặp")
for question, answer in sections.FAQ:
    with st.expander(question):
        st.write(answer)

st.html(card(
    "<b>Sẵn sàng tìm lựa chọn phù hợp với bạn?</b>"
    f'<div class="lumi-caption" style="margin-top:6px">{esc("Khoảng 3–5 phút trò chuyện.")}</div>'
))
if st.button("Bắt đầu trò chuyện ngay", type="primary"):
    st.session_state["lumi_mode"] = "manual"
    st.session_state.pop("lumi_persona", None)
    st.switch_page("pages/consult.py")

st.html(sections.footer())
