"""Static HTML for the landing page sections (lumi-ui-design.md §4).

No testimonials, no user counts, no real insurer logos — the demo has no data
to back any of those.
"""

from __future__ import annotations

from ui.components import esc

PERSONAS = [
    {
        "id": "vuong",
        "initial": "V",
        "name": "Vương, 22",
        "css": "persona-young",
        "situation": "Vừa tốt nghiệp, sắp đi làm ở một startup.",
        "insight": "Năm đầu đi làm chưa được bảo hiểm thất nghiệp bảo vệ.",
        "recommendation": "Bảo vệ thu nhập khi mất việc",
    },
    {
        "id": "mai",
        "initial": "M",
        "name": "Chị Mai, 44",
        "css": "persona-mid",
        "situation": "Kinh doanh tự do, có 8 năm BHXH cũ chưa rút.",
        "insight": "Năm thứ hai của hợp đồng trùng năm con vào đại học.",
        "recommendation": "Hưu trí",
    },
    {
        "id": "duc",
        "initial": "Đ",
        "name": "Ông Đức, 60",
        "css": "persona-senior",
        "situation": "Sang năm nghỉ hưu, vợ không có thu nhập riêng.",
        "insight": "Nếu ông mất, thu nhập của bà về 0.",
        "recommendation": "Nhân thọ",
    },
]

COMMITMENTS = [
    ("Giải thích vì sao", "LUMI nói rõ vì sao hỏi và vì sao đề xuất."),
    ("Nêu cả điểm bất lợi", "Mỗi lựa chọn đều kèm điều cần lưu ý."),
    ("Bạn quyết định", "LUMI không bán bảo hiểm."),
]

STEPS = [
    ("Trò chuyện", "Trả lời vài câu hỏi như nói chuyện với người quen. LUMI chỉ hỏi điều cần cho hoàn cảnh của bạn."),
    ("LUMI hiểu bạn", "Hồ sơ của bạn được điền dần, mỗi thông tin đều ghi rõ lấy từ câu nào bạn nói."),
    ("Đề xuất 2 bước", "Trước hết là loại bảo hiểm phù hợp và lý do. Sau đó mới so sánh sản phẩm."),
]

BEHIND = [
    ("Ngôn ngữ", "Mô hình ngôn ngữ hiểu câu trả lời và viết lời tư vấn."),
    ("Quyết định", "Một agent riêng chỉ được chọn trong các phương án định sẵn, kèm xác suất ước lượng."),
    ("Tính toán", "Code lọc sản phẩm, tính trọng số và ước tính số tiền."),
]

FAQ = [
    ("LUMI có bán bảo hiểm không?", "Không. LUMI giúp bạn hiểu nhu cầu và so sánh lựa chọn; việc mua cần làm với tư vấn viên có chứng chỉ của doanh nghiệp bảo hiểm."),
    ("Thông tin tôi chia sẻ được dùng thế nào?", "Chỉ dùng trong buổi tư vấn này để đề xuất. Bạn có thể xoá hồ sơ bất kỳ lúc nào."),
    ("LUMI tư vấn những loại bảo hiểm nào?", "Bảo vệ thu nhập khi mất việc, hưu trí và nhân thọ; sức khoẻ ở mức bổ sung."),
    ("Số liệu sản phẩm có chính xác không?", "Trong bản demo, doanh nghiệp và sản phẩm là hư cấu, số liệu chỉ để minh hoạ."),
    ("Mất bao lâu?", "Khoảng 3–5 phút trò chuyện."),
]


def hero() -> str:
    return (
        '<div class="lumi-hero">'
        '<span class="lumi-demo-badge">Bản demo · dữ liệu minh hoạ</span>'
        "<h1>Hiểu bạn trước,<br>rồi mới đề xuất.</h1>"
        "<p>LUMI trò chuyện để hiểu hoàn cảnh của bạn — công việc, gia đình, nỗi lo và ngân sách — "
        "rồi đề xuất loại bảo hiểm phù hợp và so sánh minh bạch các lựa chọn.</p>"
        '<p class="lumi-caption">Miễn phí · Không cần đăng ký · Thông tin chỉ dùng cho buổi tư vấn này</p>'
        "</div>"
    )


def commitments() -> str:
    items = "".join(
        f'<div class="lumi-step"><b>✓ {esc(title)}</b>'
        f'<div class="lumi-caption" style="margin-top:6px">{esc(text)}</div></div>'
        for title, text in COMMITMENTS
    )
    return f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">{items}</div>'


def how_it_works() -> str:
    items = "".join(
        f'<div class="lumi-step"><span class="lumi-step-number">{index}</span>'
        f"<b>{esc(title)}</b><div class=\"lumi-caption\" style=\"margin-top:6px\">{esc(text)}</div></div>"
        for index, (title, text) in enumerate(STEPS, start=1)
    )
    return f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px">{items}</div>'


def persona_card(persona: dict[str, str]) -> str:
    return (
        f'<div class="lumi-persona-card {persona["css"]}">'
        f'<span class="lumi-avatar">{esc(persona["initial"])}</span>'
        f'<div style="margin-top:10px"><b>{esc(persona["name"])}</b></div>'
        f'<div class="lumi-caption" style="margin:6px 0">{esc(persona["situation"])}</div>'
        f'<div class="lumi-insight" style="margin-top:8px">💡 LUMI nhận ra: {esc(persona["insight"])}</div>'
        f'<div><span class="lumi-tag lumi-tag-note">{esc(persona["recommendation"])}</span></div>'
        "</div>"
    )


def behind() -> str:
    items = "".join(
        f'<div class="lumi-step"><b>{esc(title)}</b>'
        f'<div class="lumi-caption" style="margin-top:6px">{esc(text)}</div></div>'
        for title, text in BEHIND
    )
    return (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px">{items}</div>'
        '<div class="lumi-caption" style="margin-top:10px">Con số trong lời tư vấn luôn đến từ dữ liệu '
        "hoặc phép tính, không do mô hình tự viết ra.</div>"
    )


def footer() -> str:
    return (
        '<div class="lumi-footer-note">'
        "Thông tin trên LUMI chỉ mang tính tham khảo, không thay thế tư vấn của tư vấn viên có chứng chỉ. "
        "Doanh nghiệp và sản phẩm trong bản demo là hư cấu."
        "</div>"
    )
