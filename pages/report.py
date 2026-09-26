"""Printable advisory report (lumi-ui-design.md §6.1)."""

from __future__ import annotations

import streamlit as st

from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from ui import components as ui

persona_id = st.session_state.get("lumi_persona")
ui.app_header(st, "report", report_ready=bool(persona_id))

if not persona_id:
    st.html(ui.page_intro(
        "Báo cáo tư vấn",
        "Báo cáo sẽ xuất hiện sau khi bạn hoàn thành một hành trình",
        "Hãy mở một phiên mẫu hoặc bắt đầu tư vấn để LUMI có đủ thông tin tạo bản tóm tắt.",
    ))
    st.info("Chưa có phiên tư vấn nào được chọn.", icon=":material/info:")
    ui.page_link(
        st,
        "pages/consult.py",
        label="Đi tới trang Tư vấn",
        icon=":material/arrow_forward:",
        use_container_width=False,
    )
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

st.html('<div class="lumi-eyebrow">Tài liệu mang về</div>')
st.title(f"Báo cáo tư vấn dành cho {name}")
st.caption("Tóm tắt những gì LUMI đã hiểu, đề xuất và các câu hỏi bạn nên kiểm tra trước khi quyết định.")

controls = st.columns([1.3, 1.3, 4])
with controls[0]:
    ui.page_link(
        st,
        "pages/consult.py",
        label="Về hội thoại",
        icon=":material/arrow_back:",
        use_container_width=True,
    )
with controls[1]:
    if st.button(
        "In / Lưu PDF",
        icon=":material/print:",
        use_container_width=True,
        type="primary",
    ):
        st.html("<script>window.parent.print();</script>")

st.divider()

st.subheader("1. Hồ sơ tóm tắt")
st.caption("Mỗi thông tin đều có thể truy ngược về câu nói trong cuộc trò chuyện.")
ui.render(st, ui.profile_chips(profile, labels))

insights = data.get("insights") or []
if insights:
    st.subheader("2. Những điều LUMI nhận ra")
    ui.render(st, ui.insight_cards(insights))

decision = data.get("type_decision")
if decision:
    st.subheader("3. Loại bảo hiểm được đề xuất")
    ui.render(st, ui.step_one_card(decision, insights, type_names.get(decision["insurance_type"], "")))

ranking = recording.ranking
if ranking:
    st.subheader("4. Hai lựa chọn đầu")
    st.caption("Thứ hạng phản ánh các ưu tiên được ghi nhận trong chính phiên tư vấn này.")
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
    st.subheader("5. Tình huống minh hoạ")
    ui.render(st, ui.scenario_card(scenario))

st.subheader("6. Câu hỏi nên hỏi tư vấn viên")
st.caption("Đánh dấu khi bạn đã nhận được câu trả lời rõ ràng.")
for index, question in enumerate([
    "Sản phẩm này loại trừ những trường hợp nào?",
    "Nếu tôi tạm dừng đóng phí thì quyền lợi thay đổi ra sao?",
    "Phí thực tế cho hồ sơ của tôi là bao nhiêu sau khi thẩm định?",
]):
    st.checkbox(question, key=f"ask_{index}")

st.subheader("7. Việc nên làm tiếp")
for index, step in enumerate([
    "Đọc kỹ quy tắc và điều khoản, nhất là phần loại trừ.",
    "Khai báo trung thực tình trạng sức khoẻ.",
    "Trao đổi với tư vấn viên có chứng chỉ trước khi ký.",
]):
    st.checkbox(step, key=f"todo_{index}")

ui.render(st, ui.data_footer())
