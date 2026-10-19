# Ví dụ 3: vì sao hai đơn giá khác nhau? (do vật tư)

> Một agent Claude trả lời bằng cách gọi các tool MCP của dự án này trên bộ dữ liệu `data/sample/` (24 công trình giả).
> Số liệu lấy nguyên từ kết quả tool. Chạy ngày 2026-10-20.

**Câu hỏi:** Vì sao đơn giá chống thấm sân thượng ở Biệt thự Sen Vàng cao hơn Biệt thự Lúa Non?

**Các lần gọi tool:**
1. `run_readonly_sql` để tìm `item_id` của hai hạng mục "Chống thấm sân thượng" ở hai công trình.
2. `compare_work_item_detail` với `{"item_id_a": 1, "item_id_b": 5}` (A = Lúa Non, B = Sen Vàng)

**Trả lời:**

Đơn giá của Sen Vàng là 244.814,83 đ, của Lúa Non là 146.457,55 đ. Sen Vàng cao hơn 98.357,28 đ, tức 67,16%. Nguyên nhân chính là vật liệu:
- Đơn giá vật liệu của Sen Vàng là 158.427,89 đ, còn Lúa Non là 77.807,17 đ, chênh 80.620,72 đ.
- Sen Vàng dùng "AnTâm Seal PU đàn hồi", đơn giá 73.113,21 đ/m². Lúa Non dùng "AnTâm Seal gốc xi măng polymer", đơn giá 35.652,17 đ/m².
- Cả hai đều thi công 2 lớp. Tổng tiền vật liệu theo diện tích là 26.319.000 đ ở Sen Vàng và 13.546.400 đ ở Lúa Non.

Các yếu tố khác gần như không tạo ra chênh lệch:
- Đơn giá nhân công của hai bên bằng nhau (42.240 đ).
- Tỷ lệ lợi nhuận bằng nhau (22%).
- Hệ số nhân công bằng nhau (1,1).
- Số ngày công của Sen Vàng thậm chí hơi thấp hơn (10,8 so với 11,4 ngày công đội nhà).
- Diện tích Sen Vàng là 180 m², Lúa Non là 190 m².

Lưu ý: ba khoản chênh (vật liệu, nhân công, lợi nhuận) không cộng thẳng ra mức chênh giá, vì giá cuối được nhân thêm hệ số lợi nhuận. Dữ liệu không có thông tin về hiện trạng thực tế của sân thượng, nên chỉ kết luận được dựa trên vật liệu và nhân công như trên.

---

**Ghi chú:** mọi con số đã được đối chiếu với kết quả tool. Tool tính các trường `*_diff` là B trừ A.

**Tự kiểm chứng:** `python3 -m scripts.mcp_call compare_work_item_detail '{"item_id_a": 1, "item_id_b": 5}'`.
