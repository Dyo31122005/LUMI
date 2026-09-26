"""LUMI product landing page."""

from __future__ import annotations

import streamlit as st

from ui import components as ui
from ui import landing_sections as sections


def open_manual() -> None:
    st.session_state["lumi_mode"] = "manual"
    st.session_state.pop("lumi_persona", None)
    st.switch_page("pages/consult.py")


def open_replay(persona_id: str) -> None:
    st.session_state["lumi_mode"] = "replay"
    st.session_state["lumi_persona"] = persona_id
    st.switch_page("pages/consult.py")


ui.app_header(st, "landing")

with st.container(key="lumi_hero_section"):
    copy, visual = st.columns([1.12, 0.88], gap="large", vertical_alignment="center")
    with copy:
        st.html(sections.hero())
        primary, secondary = st.columns([1.08, 0.92])
        with primary:
            if st.button(
                "Bắt đầu tư vấn",
                type="primary",
                icon=":material/arrow_forward:",
                use_container_width=True,
            ):
                open_manual()
        with secondary:
            if st.button(
                "Xem hành trình mẫu",
                icon=":material/play_circle:",
                use_container_width=True,
            ):
                open_replay("mai")
    with visual:
        with st.container(key="lumi_mascot_hero"):
            st.image(
                str(ui.MASCOT_PATH),
                caption="LUMI · Trợ lý tư vấn bảo hiểm cá nhân hoá",
                use_container_width=True,
            )

st.html(sections.commitments())

st.html(sections.problem_statement())

st.html(ui.page_intro(
    "Quy trình rõ ràng",
    "Từ câu chuyện của bạn đến một đề xuất có thể kiểm chứng",
    "Bạn luôn nhìn thấy LUMI đã hiểu gì, đang cân nhắc gì và vì sao một lựa chọn được xếp hạng cao hơn.",
))
st.html(sections.how_it_works())

st.html(ui.page_intro(
    "Cá nhân hoá trong thực tế",
    "Cùng một lời chào, ba hành trình khác nhau",
    "Chọn một nhân vật để xem lại toàn bộ cuộc trò chuyện và kết quả tư vấn tương ứng.",
))

columns = st.columns(3, gap="medium")
for column, persona in zip(columns, sections.PERSONAS):
    with column:
        st.html(sections.persona_card(persona))
        if st.button(
            f"Xem hành trình của {persona['name'].split(',')[0]}",
            key=f"go_{persona['id']}",
            icon=":material/arrow_outward:",
            use_container_width=True,
        ):
            open_replay(persona["id"])

st.caption("Các nhân vật, doanh nghiệp và sản phẩm trong demo đều là hư cấu.")

st.html(ui.page_intro(
    "Minh bạch từ thiết kế",
    "Bạn không cần tin vào một hộp đen",
    "Các phần quan trọng của phiên tư vấn được hiển thị ngay trong giao diện, bằng ngôn ngữ dễ hiểu.",
))
st.html(sections.feature_grid())

with st.expander("LUMI hoạt động phía sau như thế nào?", icon=":material/schema:"):
    st.html(sections.behind())

st.html(ui.page_intro(
    "Giải đáp nhanh",
    "Câu hỏi thường gặp",
    "Những điều bạn nên biết trước khi bắt đầu một phiên tư vấn.",
))
for question, answer in sections.FAQ:
    with st.expander(question):
        st.write(answer)

with st.container(key="lumi_final_cta"):
    callout, action = st.columns([2.6, 1], gap="large", vertical_alignment="center")
    with callout:
        st.html(sections.closing_cta())
    with action:
        if st.button(
            "Bắt đầu trò chuyện",
            type="primary",
            icon=":material/forum:",
            use_container_width=True,
        ):
            open_manual()

st.html(sections.footer())
