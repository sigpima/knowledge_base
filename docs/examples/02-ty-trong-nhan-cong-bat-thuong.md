# Ví dụ 2: tỷ trọng nhân công có bất thường không?

> Một agent Claude trả lời bằng cách gọi các tool MCP của dự án này trên bộ dữ liệu `data/sample/` (24 công trình giả).
> Số liệu lấy nguyên từ kết quả tool. Chạy ngày 2026-10-20.

**Câu hỏi:** Chi phí nhân công chiếm bao nhiêu % tổng báo giá của Văn phòng Ngọc Lan, có bất thường so với các công trình khác không?

**Các lần gọi tool:**
1. `run_readonly_sql` để tìm `project_id`: `SELECT project_id, name FROM quotation.project WHERE name ILIKE '%Ngọc Lan%'`
2. `get_project_overview` với `{"project_id": 24}`
3. `compare_project_cost_breakdown` với `{"project_id": 24, "cost_type": "labor"}`

**Trả lời:**

Ở Văn phòng Ngọc Lan, nhân công là 511.840.550 đ trên tổng báo giá 939.141.439,80 đ, tức chiếm 54,50%.

So với 22 công trình có dự toán để so sánh:
- Mức trung bình là 36,64%.
- Thấp nhất là 26,43%.
- Cao nhất (trước Ngọc Lan) là 53,87%, của Trường học Ánh Sao.
- Ngọc Lan cao hơn trung bình 17,86 điểm phần trăm.

Vậy tỷ lệ nhân công của Ngọc Lan là bất thường theo hướng cao: 54,50% vượt cả mức cao nhất của các công trình còn lại (53,87%). Nhóm gần nhất có Nhà phố An Phú 49,69% và Nhà phố Bạch Dương 48,58%.

Dữ liệu cũng cho thấy khối lượng nhân công của công trình này lớn: tổng 1.307,54 ngày công, trong đó 936,25 ngày công thuê ngoài và 371,29 ngày công của đội nhà. Các khoản còn lại của Ngọc Lan là vật tư (24,90%) và lợi nhuận thuần (16,23%). Tool không cho biết lý do cụ thể khiến tỷ lệ nhân công cao.

---

**Ghi chú:** mọi con số đã được đối chiếu với kết quả tool. Lưu ý "22 công trình" là số công trình có dự toán (nhà xưởng Thành Công không có dự toán nên không nằm trong so sánh).

**Tự kiểm chứng:** `python3 -m scripts.mcp_call compare_project_cost_breakdown '{"project_id": 24, "cost_type": "labor"}'`.
