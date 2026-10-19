# Ví dụ 4: vì sao hai đơn giá khác nhau? (do nhân công thuê ngoài)

> Một agent Claude trả lời bằng cách gọi các tool MCP của dự án này trên bộ dữ liệu `data/sample/` (24 công trình giả).
> Số liệu lấy nguyên từ kết quả tool. Chạy ngày 2026-10-20.

**Câu hỏi:** Vì sao đơn giá chống thấm sân thượng của Nhà phố Bạch Dương cao hơn Nhà phố Liên Hoa?

**Các lần gọi tool:**
1. `run_readonly_sql` để tìm `item_id` của hai hạng mục "Chống thấm sân thượng" ở hai công trình.
2. `compare_work_item_detail` với `{"item_id_a": 108, "item_id_b": 104}` (A = Liên Hoa, B = Bạch Dương)

**Trả lời:**

Đơn giá của Bạch Dương là 215.248,03 đ, của Liên Hoa là 157.152,42 đ. Bạch Dương cao hơn 58.095,61 đ, tức 36,97%. Nguyên nhân chính là nhân công:
- Đơn giá nhân công của Bạch Dương là 93.060 đ, còn Liên Hoa là 32.480,92 đ, chênh 60.579,08 đ.
- Liên Hoa dùng thợ của đội nhà: 12,51 ngày công đội nhà và 4,17 ngày công thợ phụ thuê ngoài.
- Bạch Dương thuê ngoài hoàn toàn: 0 ngày công đội nhà, 15,75 ngày công thợ chính thuê ngoài và 15,75 ngày công thợ phụ thuê ngoài. Thợ thuê ngoài đông hơn, ví dụ bước "Xử lý bề mặt" dùng 3 thợ chính và 3 thợ phụ thuê ngoài, trong khi Liên Hoa dùng 3 thợ đội nhà và 1 thợ phụ.

Vật liệu đi theo chiều ngược lại và làm giá của Bạch Dương thấp bớt đi:
- Đơn giá vật liệu của Bạch Dương là 83.372,81 đ, thấp hơn Liên Hoa (96.332,54 đ) 12.959,73 đ.
- Cả hai đều dùng cùng sản phẩm "AnTâm Seal gốc xi măng polymer", 2 lớp. Đơn giá của Bạch Dương là 39.423,08 đ/m², còn Liên Hoa là 44.565,22 đ/m².

Các yếu tố khác không tạo chênh lệch: tỷ lệ lợi nhuận bằng nhau (22%), hệ số nhân công bằng nhau (1,1). Diện tích là 175 m² (Bạch Dương) và 185 m² (Liên Hoa). Dữ liệu không có thông tin về hiện trạng thực tế của sân thượng, nên chỉ kết luận được dựa trên vật liệu và nhân công như trên.

---

**Ghi chú:** mọi con số đã được đối chiếu với kết quả tool. Tool tính các trường `*_diff` là B trừ A.

**Tự kiểm chứng:** `python3 -m scripts.mcp_call compare_work_item_detail '{"item_id_a": 108, "item_id_b": 104}'`.
