# Deploy LUMI lên Railway

## Vì sao không dùng Vercel

Streamlit cần một tiến trình chạy liên tục và giữ kết nối WebSocket với trình
duyệt cho suốt phiên làm việc. Vercel chạy serverless function: mỗi request là
một lần gọi ngắn, có giới hạn thời gian, không giữ kết nối lâu dài. Đây là khác
biệt về kiến trúc, không phải chuyện cấu hình, nên **không deploy LUMI lên Vercel
được**.

Các nền tảng chạy được: **Railway**, Render, Fly.io, Google Cloud Run, hoặc
Streamlit Community Cloud.

## Chuẩn bị: tách LUMI thành repo riêng

Hiện `lumi/` nằm lồng trong repo `BIVA-challenge`, mà repo đó là dự án Node
(`codex-with-chatgpt`) có `package.json` ở gốc. Railway sẽ nhìn thấy
`package.json` và build thành ứng dụng Node. Vì vậy LUMI cần repo của riêng nó.

Thư mục `lumi/` đã được chuẩn bị để tự chứa: knowledge base nay nằm ở
`data/lumi_knowledge_base.yaml` bên trong thư mục ứng dụng, nên chỉ cần copy
thư mục này ra là chạy được.

```bash
# Từ thư mục cha của lumi/
cp -r lumi ../lumi-app
cd ../lumi-app

# Kiểm tra trước khi đẩy lên
python -m venv .venv && source .venv/bin/activate   # Windows: .venv/Scripts/activate
pip install -r requirements-dev.txt
python -m pytest tests -q          # phải pass toàn bộ, không cần mạng
streamlit run app.py               # mở thử localhost:8501

git init
git add .
git commit -m "LUMI: chatbot tư vấn bảo hiểm cá nhân hoá"
git remote add origin https://github.com/<tài-khoản>/lumi.git
git push -u origin main
```

Trước khi push, chạy `git status` và xác nhận **`.env` không nằm trong danh sách**
(file này đã có trong `.gitignore`).

## Các file phục vụ deploy

| File | Vai trò |
|---|---|
| `Procfile` | Lệnh khởi động; bind vào `$PORT` mà Railway cấp và `0.0.0.0` |
| `.python-version` | Pin Python 3.12 để Railway không tự chọn bản khác |
| `requirements.txt` | Chỉ dependency chạy production |
| `requirements-dev.txt` | Thêm pytest và pyflakes cho lúc phát triển |
| `.streamlit/config.toml` | `headless = true`, tắt telemetry, màu thương hiệu |
| `.env.example` | Danh sách biến môi trường cần đặt |

Máy bạn đang chạy Python 3.14.6 còn bản deploy pin 3.12. Mã chỉ dùng tính năng từ
3.11 trở xuống (`StrEnum` là thứ mới nhất) nên tương thích, nhưng hãy chạy lại
test trên môi trường 3.12 nếu muốn chắc chắn.

## Tạo service trên Railway

1. Railway → **New Project** → **Deploy from GitHub repo** → chọn repo `lumi` vừa tạo.
2. Railway tự nhận Python qua `requirements.txt` và dùng `Procfile` làm lệnh chạy.
   Không cần đặt Root Directory vì repo đã chỉ chứa ứng dụng.
3. Vào tab **Variables** và đặt các biến ở mục dưới.
4. Tab **Settings** → **Networking** → **Generate Domain** để lấy URL công khai.

## Biến môi trường

| Biến | Giá trị | Bắt buộc |
|---|---|---|
| `OPENAI_API_KEY` | Key OpenAI của bạn | Có, nếu muốn chạy AI thật |
| `MODEL` | `gpt-5.6-luna` | Có |
| `MODEL_WRITER` | `gpt-5.6-luna` | Có |
| `DECISION_ENGINE` | `openai` | Có |
| `LUMI_APP_PASSWORD` | Mật khẩu bạn tự đặt | **Có** khi deploy công khai |
| `LUMI_VOICE` | `on` hoặc `off` | Không, mặc định `on` |
| `MODEL_STT` | `gpt-4o-transcribe` | Không, có mặc định |
| `MODEL_TTS` | `gpt-4o-mini-tts` | Không, có mặc định |
| `LUMI_VOICE_MAX_ACTIONS` | Số nguyên, mặc định `20` | Không |

`PORT` do Railway tự cấp, đừng đặt tay.

## Về mật khẩu bảo vệ

Đặt `LUMI_APP_PASSWORD` thì toàn bộ trang sẽ hỏi mật khẩu trước khi vào. Cơ chế
nằm ở `core/gate.py` và so sánh bằng `hmac.compare_digest` để không bị dò qua
thời gian phản hồi.

Cần nói rõ giới hạn: **đây là rào nhẹ, không phải xác thực thật.** Không có tài
khoản, không có phiên đăng nhập phía server, không giới hạn số lần thử, và mật
khẩu dùng chung cho mọi người. Nó đủ để ngăn người lạ tình cờ mở link và tiêu
hết hạn mức API của bạn, nhưng không chống được người cố tình tấn công.

Nếu không đặt biến này, trang mở công khai — khi đó **bất kỳ ai có link đều tiêu
tiền API của bạn**.

## Giọng nói và chi phí

Mỗi lượt dùng giọng nói tốn thêm một lần phiên âm và một lần tổng hợp giọng,
ngoài các lời gọi vốn có. Nếu muốn mở link cho nhiều người mà vẫn giữ chi phí
thấp, đặt `LUMI_VOICE=off`; phần gõ phím hoạt động y nguyên.

Nếu vẫn muốn bật giọng nói, `LUMI_VOICE_MAX_ACTIONS` đặt trần số lượt mỗi phiên
(mặc định 20; một lượt là một lần phiên âm hoặc một lần đọc). Hết trần thì micro
và nút Nghe biến mất kèm lời giải thích, phần gõ phím giữ nguyên. Âm thanh đã
sinh được dùng lại nên nghe lại một câu cũ không tốn thêm lượt.

Hai model audio là ngoại lệ có chủ đích với quy tắc một model duy nhất trong
build plan: model hội thoại không phiên âm và không đọc được. Mọi agent suy nghĩ
và viết vẫn dùng đúng `gpt-5.6-luna`.

## Việc phải làm ở phía OpenAI

Đặt **spending limit** trong trang quản lý tài khoản OpenAI trước khi mở link cho
người khác. Mật khẩu giảm rủi ro chứ không loại bỏ nó; giới hạn chi tiêu là lớp
chặn cuối cùng. Một phiên tư vấn khoảng 10 lượt tốn chừng 0,04–0,08 USD.

## Sau khi deploy

- [ ] Mở URL, xác nhận trang hỏi mật khẩu.
- [ ] Vào được, thử chế độ **Phát lại** với cả ba nhân vật.
- [ ] Thử chế độ **Tự trò chuyện**, gõ một câu và xem LUMI có trả lời không.
- [ ] Nếu Tự trò chuyện báo lỗi kết nối, kiểm tra lại `OPENAI_API_KEY` trong Variables.
- [ ] Xem log Railway, không có traceback.

## Phương án dự phòng: deploy không cần API key

Nếu chỉ cần trình diễn, bỏ trống `OPENAI_API_KEY` và đặt `DECISION_ENGINE=rule`.
Chế độ Phát lại vẫn chạy đầy đủ vì đọc từ `data/recordings/`, còn chế độ Tự trò
chuyện sẽ hiện thông báo kèm nút chuyển sang Phát lại. Cách này không tốn đồng
nào và không có rủi ro lộ hạn mức.
