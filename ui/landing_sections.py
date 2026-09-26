"""Static, data-safe sections for the LUMI landing page."""

from __future__ import annotations

from ui.components import esc, material_icon

PERSONAS = [
    {"id": "vuong", "initial": "V", "name": "Vương, 22", "css": "persona-young", "situation": "Vừa tốt nghiệp, sắp đi làm ở một startup.", "insight": "Năm đầu đi làm chưa được bảo hiểm thất nghiệp bảo vệ.", "recommendation": "Bảo vệ thu nhập khi mất việc"},
    {"id": "mai", "initial": "M", "name": "Chị Mai, 44", "css": "persona-mid", "situation": "Kinh doanh tự do, có 8 năm BHXH cũ chưa rút.", "insight": "Năm thứ hai của hợp đồng trùng năm con vào đại học.", "recommendation": "Hưu trí"},
    {"id": "duc", "initial": "Đ", "name": "Ông Đức, 60", "css": "persona-senior", "situation": "Sang năm nghỉ hưu, vợ không có thu nhập riêng.", "insight": "Nếu ông mất, thu nhập của bà về 0.", "recommendation": "Nhân thọ"},
]

COMMITMENTS = [
    ("psychology", "Hỏi vừa đủ", "Mỗi câu hỏi đều có lý do và phục vụ trực tiếp cho đề xuất."),
    ("balance", "So sánh minh bạch", "Điểm mạnh, điểm cần lưu ý và giả định được đặt cạnh nhau."),
    ("verified_user", "Bạn giữ quyền quyết định", "LUMI không bán bảo hiểm và không thay thế tư vấn viên có chứng chỉ."),
]

STEPS = [
    ("forum", "Chia sẻ hoàn cảnh", "Bạn nói về công việc, gia đình, nỗi lo và ngân sách theo cách tự nhiên."),
    ("manage_accounts", "Xem hồ sơ được hiểu", "Thông tin được điền dần và luôn gắn với câu nói gốc của bạn."),
    ("fact_check", "Nhận đề xuất hai bước", "LUMI chọn loại bảo hiểm trước, rồi mới so sánh sản phẩm theo ưu tiên cá nhân."),
]

FEATURES = [
    ("visibility", "Nhìn thấy cách LUMI suy luận", "Theo dõi hồ sơ, nhận định và các khả năng đang được cân nhắc trong suốt cuộc trò chuyện."),
    ("tune", "So sánh theo điều bạn quan tâm", "Các tiêu chí quan trọng với bạn được đưa lên trước thay vì dùng một bảng xếp hạng chung."),
    ("calculate", "Con số có nguồn", "Mọi con số đến từ knowledge base hoặc phép tính trong code, không do mô hình tự đặt ra."),
]

BEHIND = [
    ("chat", "Ngôn ngữ", "AI hiểu câu trả lời và diễn đạt lời tư vấn bằng tiếng Việt tự nhiên."),
    ("account_tree", "Quyết định", "Một lớp riêng chỉ chọn trong tập phương án định sẵn và trả về dữ liệu có cấu trúc."),
    ("functions", "Tính toán", "Code lọc điều kiện, tính trọng số, xếp hạng và ước tính số tiền."),
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
        '<span class="lumi-kicker">Bản demo tư vấn bảo hiểm cá nhân hoá</span>'
        '<h1>Mỗi hoàn cảnh cần một cách bảo vệ khác nhau.</h1>'
        '<p class="lumi-hero-lead">LUMI trò chuyện để hiểu điều bạn đang lo, khả năng tài chính và người bạn muốn bảo vệ. Sau đó mới đề xuất loại bảo hiểm và so sánh lựa chọn phù hợp.</p>'
        '<div class="lumi-inline-proof">'
        f'{material_icon("lock")} Không cần đăng ký<span aria-hidden="true"></span>'
        f'{material_icon("schedule")} Khoảng 3–5 phút<span aria-hidden="true"></span>'
        f'{material_icon("delete")} Có thể xoá hồ sơ'
        '</div></div>'
    )


def commitments() -> str:
    items = "".join(
        '<article class="lumi-proof-item">'
        f'<span class="lumi-icon-box">{material_icon(icon)}</span>'
        f'<div><b>{esc(title)}</b><p>{esc(text)}</p></div></article>'
        for icon, title, text in COMMITMENTS
    )
    return f'<div class="lumi-proof-strip">{items}</div>'


def problem_statement() -> str:
    return (
        '<div class="lumi-statement"><div class="lumi-eyebrow">Một cách tiếp cận khác</div>'
        '<h2>Bảo hiểm nên bắt đầu từ cuộc sống của bạn, không phải từ danh sách sản phẩm.</h2>'
        '<p>LUMI tách rõ ba việc: lắng nghe, quyết định có cấu trúc và tính toán bằng code. Nhờ vậy, bạn có thể nhìn thấy vì sao một lựa chọn được đưa ra.</p></div>'
    )


def how_it_works() -> str:
    items = "".join(
        '<article class="lumi-step">'
        f'<div class="lumi-step-head"><span class="lumi-step-number">{index}</span>{material_icon(icon)}</div>'
        f'<h3>{esc(title)}</h3><p>{esc(text)}</p></article>'
        for index, (icon, title, text) in enumerate(STEPS, start=1)
    )
    return f'<div class="lumi-grid lumi-grid-3">{items}</div>'


def persona_card(persona: dict[str, str]) -> str:
    return (
        f'<article class="lumi-persona-card {persona["css"]}">'
        '<div class="lumi-persona-head">'
        f'<span class="lumi-avatar">{esc(persona["initial"])}</span>'
        f'<div><h3>{esc(persona["name"])}</h3><p>{esc(persona["situation"])}</p></div></div>'
        '<div class="lumi-persona-insight">'
        f'{material_icon("lightbulb")}<div><small>LUMI nhận ra</small><p>{esc(persona["insight"])}</p></div></div>'
        f'<span class="lumi-tag lumi-tag-note">{esc(persona["recommendation"])}</span>'
        '</article>'
    )


def feature_grid() -> str:
    items = "".join(
        '<article class="lumi-feature-card">'
        f'<span class="lumi-icon-box">{material_icon(icon)}</span>'
        f'<h3>{esc(title)}</h3><p>{esc(text)}</p></article>'
        for icon, title, text in FEATURES
    )
    return f'<div class="lumi-grid lumi-grid-3">{items}</div>'


def behind() -> str:
    items = "".join(
        '<article class="lumi-system-node">'
        f'<span>{material_icon(icon)}</span><div><b>{esc(title)}</b><p>{esc(text)}</p></div></article>'
        for icon, title, text in BEHIND
    )
    return f'<div class="lumi-system-flow">{items}</div><p class="lumi-caption lumi-center">Con số trong lời tư vấn luôn đến từ dữ liệu hoặc phép tính, không do mô hình tự viết ra.</p>'


def closing_cta() -> str:
    return (
        '<div class="lumi-closing-cta"><div><div class="lumi-eyebrow">Bắt đầu khi bạn sẵn sàng</div>'
        '<h2>Tìm lựa chọn phù hợp với chính hoàn cảnh của bạn.</h2>'
        '<p>Không cần chuẩn bị hồ sơ. Hãy bắt đầu bằng điều bạn đang quan tâm nhất.</p></div></div>'
    )


def footer() -> str:
    return (
        '<footer class="lumi-footer"><div class="lumi-footer-brand"><span class="lumi-brand-mark" aria-hidden="true"></span><b>LUMI</b></div>'
        '<p>Thông tin trên LUMI chỉ mang tính tham khảo, không thay thế tư vấn của tư vấn viên có chứng chỉ. Doanh nghiệp và sản phẩm trong bản demo là hư cấu.</p>'
        '<small>Demo sản phẩm · 2026</small></footer>'
    )
