# Checklist trình diễn LUMI (5 phút)

## Chuẩn bị trước khi bắt đầu

- [ ] `streamlit run app.py` chạy được, mở ở `http://localhost:8501`.
- [ ] Ba recording có trong `data/recordings/`: `vuong.json`, `mai.json`, `duc.json`.
- [ ] Chạy `python -m pytest tests -q` — toàn bộ pass, không cần mạng.
- [ ] Nếu mạng yếu: chỉ dùng chế độ **Phát lại**; chế độ này không gọi API.
- [ ] Phóng to trình duyệt đến mức chữ đọc được từ xa; tắt thông báo hệ thống.

## Kịch bản 5 phút

| Thời gian | Thao tác | Nói gì |
|---|---|---|
| 0:00–0:30 | Landing | LUMI hỏi để hiểu từng người rồi mới đề xuất. Chỉ vào ba thẻ nhân vật. |
| 0:30–2:00 | Bấm thẻ **Vương** | Chỉ vào chip hồ sơ có câu trích, thanh giả thuyết nghiêng về “Thất nghiệp”, và dòng “Vì sao LUMI hỏi câu này”. |
| 2:00–3:10 | Bấm thẻ **Chị Mai**, cuộn tới Bước 2 | Chip ưu tiên hiện “Khả năng chi trả · Mức cam kết”. Trong heatmap, ô “Linh hoạt” của Hưu An Nhàn là màu cam vì chị chỉ tạm dừng được từ năm thứ 3. |
| 3:10–3:50 | Trong hồ sơ chị Mai, bấm **Thử thay đổi thông tin** → **Thử bỏ khoản chi lớn sắp tới** | Banner ghi rõ đây là bản thử. Hưu An Nhàn đi từ hạng 2 lên hạng 1, bảng nhiệt và thẻ tài chính đổi theo. Bấm **Hoàn tác** để trở về hồ sơ gốc. Toàn bộ nhịp này chạy offline. |
| 3:50–4:35 | Bấm thẻ **Ông Đức** | Giao diện tự bật chữ lớn. Ưu tiên đổi sang “Đáp ứng nhu cầu · Điều kiện tham gia” vì ông có bệnh mãn tính. Mở thẻ “Nếu… thì…”: bà nhận được gì. |
| 4:35–5:00 | Mở trang **3 hành trình** | Cùng một lời chào, ba hồ sơ, ba đề xuất khác nhau. |

## Nếu bị hỏi kỹ thuật

> “Mô hình ngôn ngữ lo phần hội thoại; một agent quyết định riêng chỉ được chọn
> trong các phương án định sẵn; mọi con số do code tính.”

Dẫn chứng nhanh nếu cần:

- `core/scoring.py` — lọc cứng, trọng số C1–C6, điểm phù hợp.
- `core/whatif.py` — tạo bản thử riêng, chỉ tính lại phần bị ảnh hưởng và mô tả chênh lệch.
- `core/guards.py` — loại bỏ câu chứa số không có trong dữ liệu.
- `tests/test_finance.py` — công thức tài chính đối chiếu `finance.worked_examples`.
- `tests/test_scoring.py::test_ranking_follows_the_profile_rather_than_a_fixed_answer`
  — đổi hồ sơ thì thứ hạng đổi, không có đáp án cài sẵn.

## Câu hỏi hay gặp

| Câu hỏi | Trả lời |
|---|---|
| Số liệu có thật không? | Không. Doanh nghiệp và sản phẩm là hư cấu; giao diện luôn ghi nhãn. Quy định Nhà nước lấy từ nguồn ghi trong knowledge base. |
| Xác suất lấy ở đâu? | Do mô hình ước lượng, chưa được hiệu chỉnh. Giao diện ghi rõ “xác suất ước lượng” và có bảng luật đối chiếu. |
| Nếu mô hình đề xuất sai thì sao? | Có ngưỡng độ tin cậy 0,6 và bảng luật đối chiếu; lệch nhau thì LUMI hỏi thêm một câu phân định thay vì đoán. |
| LUMI có bán bảo hiểm không? | Không. Mọi lời tư vấn đều kết bằng lưu ý làm việc với tư vấn viên có chứng chỉ. |

## Sau khi trình diễn

- [ ] Không commit `.env`.
- [ ] `data/expected_report.json` ghi kết quả lần kiểm thử gần nhất.
