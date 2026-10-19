# Ví dụ 1: đơn giá có đắt so với các công trình tương tự không?

> Một agent Claude trả lời bằng cách gọi các tool MCP của dự án này trên bộ dữ liệu `data/sample/` (24 công trình giả).
> Số liệu lấy nguyên từ kết quả tool. Chạy ngày 2026-10-20. Cách tự lặp lại: xem mục "Tự kiểm chứng" cuối trang.

**Câu hỏi:** Báo giá chống thấm sân thượng của Biệt thự Sen Vàng so với các công trình tương tự thì đắt hay rẻ?

**Các lần gọi tool:**
1. `run_readonly_sql` để tìm `item_id` của hạng mục: `SELECT p.project_id, p.name, w.item_id, w.name AS item_name, w.unit_price FROM quotation.project p JOIN ... WHERE p.name ILIKE '%Sen Vàng%' ... AND w.name ILIKE '%sân thượng%'`
2. `compare_work_item_price` với `{"item_id": 5}`

**Trả lời:**

Hạng mục "Chống thấm sân thượng" của Biệt thự Sen Vàng có đơn giá 244.814,83 đ. Mức này đắt hơn mức trung bình của các công trình tương tự (222.291,19 đ) khoảng 10,1%. Tool tìm được 11 hạng mục tương tự và liệt kê 10 hạng mục gần nhất. Trong tất cả các hạng mục khớp, đơn giá thấp nhất là 146.457,55 đ và cao nhất là 330.819,06 đ.

Trong các công trình được liệt kê:
- Nhà phố Liên Hoa: 157.152,42 đ
- Biệt thự Lúa Non: 146.457,55 đ
- Trung tâm thương mại Đại Ngàn: 169.991,52 đ
- Khách sạn Hải Âu: 194.322,22 đ
- Nhà phố Bạch Dương: 215.248,03 đ
- Văn phòng Ngọc Lan: 220.871,51 đ
- Văn phòng Thanh Tùng: 234.138,24 đ
- Showroom Gia Bảo: 240.935,93 đ
- Biệt thự Bình Minh: 287.318,66 đ
- Văn phòng Đông Hưng: 330.819,06 đ

Kết luận: giá của Sen Vàng thuộc nhóm cao hơn mức trung bình, nhưng chưa phải cao nhất. Nó cao hơn 8 trong số 10 công trình được liệt kê và thấp hơn Biệt thự Bình Minh và Văn phòng Đông Hưng.

---

**Ghi chú về bản ghi này:**
- Agent gọi `run_readonly_sql` lần đầu với sai tên tham số (`sql` thay vì `query`), bị lỗi kiểm tra tham số, rồi gọi lại đúng. Lần lỗi không được liệt kê ở trên.
- Câu kết luận gốc của agent đếm sai ("cao hơn 7 trong số 10"); đối chiếu với chính danh sách trên thì đúng là 8, nên đã sửa. Mọi con số khác đã được đối chiếu với kết quả tool.

**Tự kiểm chứng:** với stack đang chạy (`docker compose up`),
`python3 -m scripts.mcp_call compare_work_item_price '{"item_id": 5}'`.
