# Nâng cấp toàn diện UI/UX LUMI

- Bắt đầu: 2026-09-27
- Trạng thái: Đang làm

## Mục tiêu

Thiết kế lại trải nghiệm LUMI theo hướng sáng, chuyên nghiệp, đáng tin cậy và dễ dùng; làm rõ đường đi từ giới thiệu đến bắt đầu tư vấn, theo dõi hồ sơ, xem đề xuất và đọc báo cáo. Giữ nguyên engine AI, schema, scoring, knowledge base và các quy tắc nghiệp vụ. Đưa `image/mascot.png` vào source production.

## Việc cần làm

- [x] UI-01 — Rà soát flow hiện tại, đặc tả và test; chốt design system cho Streamlit.
- [x] UI-02 — Đưa mascot vào asset production và tạo shell điều hướng nhất quán.
- [x] UI-03 — Thiết kế lại Landing với CTA chính, giải thích quy trình và demo persona.
- [x] UI-04 — Thiết kế lại màn bắt đầu tư vấn và màn hội thoại hai cột.
- [x] UI-05 — Chuẩn hoá thẻ hồ sơ, trạng thái, đề xuất, bảng so sánh và phản hồi lỗi.
- [x] UI-06 — Thiết kế lại trang Báo cáo và 3 hành trình theo cùng hệ thống giao diện.
- [x] UI-07 — Kiểm tra accessibility, responsive, AppTest và toàn bộ test hiện có.
- [ ] UI-08 — Review production, commit, push và xác nhận Railway deployment.

## Nhật ký

- 2026-09-27: Đọc `AGENTS.md`, task cũ, đặc tả LUMI và skill `ui-ux-pro-max`; tạo branch `feature/lumi-ui-redesign` từ `origin/main` để dễ rollback.
- 2026-09-27: Chốt design system Minimal/Swiss, palette xanh tin cậy, motion nhẹ và density chuẩn; lưu tại `design-system/lumi/MASTER.md`. Sao chép mascot gốc vào `assets/mascot.png`.
- 2026-09-27: Ẩn sidebar kỹ thuật, thêm header theo nhiệm vụ và thiết kế lại toàn bộ Landing, màn bắt đầu, hội thoại, hồ sơ, Báo cáo và Hành trình mẫu. Gợi ý mở đầu nay được gửi thật vào phiên thay vì chỉ đổi màn.
- 2026-09-27: AppTest giao diện đạt 18/18. Sau khi rebase lên ba thay đổi hội thoại mới nhất của `main`, toàn bộ dự án đạt 120/120 test; pyflakes sạch; server local khởi động và trả HTTP 200. Không sửa `core/`, `agents/`, scoring hoặc knowledge base.

## Việc tiếp theo

Tích hợp commit mới nhất từ `main`, commit thay đổi UI, push và xác nhận Railway production.
