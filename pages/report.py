"""Printable advisory report (lumi-ui-design.md §6.1)."""

from __future__ import annotations

import streamlit as st

from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from ui import components as ui

persona_id = st.session_state.get("lumi_persona")

if not persona_id:
    st.info("Mở một phiên tư vấn trước, rồi quay lại trang này.")
    if st.button("Đi tới trang Tư vấn"):
        st.switch_page("pages/consult.py")
    st.stop()

try:
    recording = Recording.load(persona_id)
except FileNotFoundError:
    st.warning(f"Chưa có phiên đã ghi cho {persona_id}.")
    st.stop()

data = recording.data
profile = Profile.model_validate(data["profile"])
name = profile.name or persona_id
kb = KnowledgeBase.load()
type_names = {item["id"]: item["name_vi"] for item in kb.section("insurance_types")}
labels = {item["key"]: item["label_vi"] for item in kb.section("profile_schema")["fields"]}

controls = st.columns([1, 1, 4])
with controls[0]:
    if st.button("← Hội thoại", use_container_width=True):
        st.switch_page("pages/consult.py")
with controls[1]:
    if st.button("In / Lưu PDF", use_container_width=True, type="primary"):
        st.html("<script>window.parent.print();</script>")

st.title(f"Báo cáo tư vấn bảo hiểm dành cho {name}")

st.subheader("1. Hồ sơ tóm tắt")
ui.render(st, ui.profile_chips(profile, labels))

insights = data.get("insights") or []
if insights:
    st.subheader("2. LUMI nhận ra")
    ui.render(st, ui.insight_cards(insights))

decision = data.get("type_decision")
if decision:
    st.subheader("3. Đề xuất")
    ui.render(st, ui.step_one_card(decision, insights, type_names.get(decision["insurance_type"], "")))

ranking = recording.ranking
if ranking:
    st.subheader("4. Hai lựa chọn đầu")
    ui.render(st, ui.ranking_cards(ranking[:2], name))

    rows = list(kb.section("comparison_rows")[decision["insurance_type"]])
    mapping = kb.section("scoring")["criterion_to_rows"][decision["insurance_type"]]
    priority_rows = [
        str(item)
        for criterion in data.get("priority_criteria", [])
        for item in mapping.get(criterion, ())
    ]
    ui.render(st, ui.comparison_table(ranking[:2], priority_rows or rows[:6], priority_rows))

scenario = data.get("scenario")
if scenario:
    st.subheader("5. Nếu… thì…")
    ui.render(st, ui.scenario_card(scenario))

st.subheader("6. Câu hỏi nên hỏi tư vấn viên")
for question in [
    "Sản phẩm này loại trừ những trường hợp nào?",
    "Nếu tôi tạm dừng đóng phí thì quyền lợi thay đổi ra sao?",
    "Phí thực tế cho hồ sơ của tôi là bao nhiêu sau khi thẩm định?",
]:
    st.checkbox(question, key=f"ask_{hash(question)}")

st.subheader("7. Việc nên làm tiếp")
for step in [
    "Đọc kỹ quy tắc và điều khoản, nhất là phần loại trừ.",
    "Khai báo trung thực tình trạng sức khoẻ.",
    "Trao đổi với tư vấn viên có chứng chỉ trước khi ký.",
]:
    st.checkbox(step, key=f"todo_{hash(step)}")

ui.render(st, ui.data_footer())
