# LUMI — Chatbot tư vấn bảo hiểm cá nhân hoá

> *"Hiểu bạn trước, rồi mới đề xuất."*

LUMI trò chuyện bằng tiếng Việt để hiểu hoàn cảnh của khách, rồi đề xuất **loại**
bảo hiểm phù hợp (Bước 1) và **so sánh sản phẩm** theo đúng điều khách quan tâm
(Bước 2). Mỗi thông tin trên hồ sơ đều kèm câu nói gốc của khách, và mỗi câu hỏi
đều nói rõ vì sao LUMI hỏi.

Đây là **bản demo**. Doanh nghiệp và sản phẩm trong catalog là hư cấu; số liệu chỉ
để minh hoạ.

## Nguyên tắc kiến trúc

Ba loại việc được giao cho ba nơi khác nhau, và ranh giới này là điều quan trọng
nhất của dự án:

| Việc | Giao cho | Ở đâu |
|---|---|---|
| Hiểu và viết ngôn ngữ | LLM tự do trong khuôn prompt | `agents/` |
| Quyết định có tập đáp án định sẵn | LLM bị ép JSON schema chặt | `core/decision.py` |
| Mọi phép tính, lọc, trọng số, xếp hạng | Code thuần | `core/scoring.py`, `core/finance.py` |

A4 (người viết lời tư vấn) chỉ nhận kết quả **đã chốt** dưới dạng JSON, nên không
thể tự đổi đề xuất khi viết. `core/guards.py` loại bỏ mọi câu chứa con số không có
trong dữ liệu đầu vào.

Chỉ dùng một model duy nhất, `gpt-5.6-luna`; các agent khác nhau ở mức
`reasoning_effort` và prompt.

## Cài đặt

```bash
cd lumi
python -m venv .venv
.venv/Scripts/activate        # Windows; Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # rồi điền OPENAI_API_KEY
```

`.env` cần:

```
OPENAI_API_KEY=sk-...
MODEL=gpt-5.6-luna
MODEL_WRITER=gpt-5.6-luna
DECISION_ENGINE=openai        # hoặc rule để chạy offline
```

`.env` đã nằm trong `.gitignore`; không commit key.

## Chạy

**Giao diện web:**

```bash
streamlit run app.py
```

Gồm 4 trang: Trang chủ, Tư vấn, Báo cáo và Hành trình mẫu. Giao diện dùng thanh
điều hướng gọn ở đầu trang, mascot LUMI và một luồng chính từ tìm hiểu sản phẩm
đến bắt đầu tư vấn, xem đề xuất rồi mở báo cáo. Chế độ **Phát lại** đọc các phiên
trong `data/recordings/` nên **chạy được khi không có mạng và không cần API key**.

**Chạy một phiên trong terminal:**

```bash
python scripts/run_cli.py --persona vuong --mode auto
python scripts/run_cli.py --persona mai --mode auto --output data/recordings/mai.json
python scripts/run_cli.py --persona duc --mode auto --engine rule   # không gọi API
```

**Kiểm thử:**

```bash
python -m pytest tests -q
```

Toàn bộ test chạy offline, không gọi OpenAI.

## Ba nhân vật demo

| Nhân vật | Hoàn cảnh | Loại đề xuất | Sản phẩm đầu bảng |
|---|---|---|---|
| Vương, 22 | Vừa tốt nghiệp, sắp vào startup, đang trả góp | Thất nghiệp | GenZ Bảo Vệ |
| Chị Mai, 44 | Tự kinh doanh, 8 năm BHXH chưa rút, con sắp vào đại học | Hưu trí | Hưu Trí Linh Hoạt |
| Ông Đức, 60 | Sắp nghỉ hưu, vợ không có thu nhập, tăng huyết áp | Nhân thọ | Bảo Tín Đóng Một Lần |

Kết quả này **không được hardcode**. Nó đến từ hồ sơ khách qua lọc cứng, trọng số
C1–C6 và điểm phù hợp. Đổi hồ sơ thì kết quả đổi theo — ví dụ nếu chị Mai không có
khoản chi lớn sắp tới thì Hưu An Nhàn vươn lên đứng đầu (xem
`tests/test_scoring.py::test_ranking_follows_the_profile_rather_than_a_fixed_answer`).

## Cấu trúc

```
lumi/
├── app.py                  # st.navigation
├── pages/                  # landing, consult, report, journeys
├── ui/                     # theme.css, components.py, landing_sections.py
├── core/
│   ├── kb.py               # nạp knowledge base read-only
│   ├── schemas.py          # Pydantic: Profile, các quyết định, session log
│   ├── llm.py              # wrapper Responses API: model, reasoning, strict schema
│   ├── decision.py         # OpenAIEngine | RuleEngine (D1–D6)
│   ├── orchestrator.py     # máy trạng thái
│   ├── scoring.py          # trường suy diễn, lọc cứng, trọng số, xếp hạng
│   ├── finance.py          # công thức tiền cho thẻ "Nếu… thì…"
│   ├── guards.py           # number guard
│   └── session_io.py       # ghi/đọc phiên để phát lại
├── agents/                 # simulator, extractor (A1), conversation (A3), writer (A4)
├── prompts/                # prompt của từng agent
├── data/                   # personas, expected.yaml, recordings
└── tests/
```

Knowledge base nằm ở `data/lumi_knowledge_base.yaml`, được nạp **chỉ đọc** và
đóng băng trong bộ nhớ. `core/kb.py` tìm theo thứ tự: biến `LUMI_KB_PATH`, rồi
`data/` trong ứng dụng, rồi `data/` ở thư mục cha — nhờ vậy ứng dụng chạy được cả
khi nằm trong repo lớn hơn lẫn khi deploy độc lập.

## Máy trạng thái

```
GREETING → DISCOVERY → RECOMMEND_TYPE → CONFIRM → COMPARE → FOLLOW_UP → CLOSING
```

- Tối đa 8 câu hỏi khám phá. Hết hạn mức, LUMI đề xuất kèm giả định thay vì hỏi thêm.
- Độ tin cậy D3 dưới 0,6 hoặc lệch với bảng luật đối chiếu thì LUMI hỏi một câu phân định.
- **Bước 2 chỉ chạy sau khi D4 nhận ra khách đồng ý**, không tự động chuyển.

## Deploy

Xem [DEPLOY.md](DEPLOY.md). Tóm tắt: Streamlit cần tiến trình chạy liên tục nên
**không deploy lên Vercel được**; dùng Railway, Render hoặc Fly.io. Khi deploy công
khai, đặt `LUMI_APP_PASSWORD` để chặn người lạ tiêu hạn mức API của bạn, và đặt
spending limit trong tài khoản OpenAI.

## Giới hạn đã biết

- Chế độ **Tự trò chuyện** gọi API theo từng lượt nên mỗi câu trả lời mất vài giây;
  chưa có hiệu ứng chữ chạy như bản thiết kế mô tả.
- Xác suất là **ước lượng của mô hình**, không được hiệu chỉnh; giao diện luôn ghi rõ.
- Quy định Nhà nước có `verified: false` hoặc `partial` chỉ được nói ở mức khái quát.
- Chưa có What-if.
- Cổng mật khẩu (`core/gate.py`) là rào nhẹ dùng chung, không phải xác thực thật:
  không có tài khoản, không giới hạn số lần thử.

## Lưu ý

Thông tin LUMI đưa ra chỉ mang tính tham khảo, không thay thế tư vấn của tư vấn
viên có chứng chỉ.
