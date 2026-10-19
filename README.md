# knowledge_base

**Hỏi đáp báo giá thi công sơn bằng agent AI.** Kho dữ liệu báo giá và dự toán trong Postgres, nạp từ file YAML có
cấu trúc, cùng một MCP server chỉ đọc để Claude, Codex hoặc agent khác trả lời kiểu *"vì sao đơn giá hạng mục này ở
công trình A cao hơn công trình B?"* kèm số liệu cụ thể.

> Toàn bộ dữ liệu trong repo là **giả lập**: công ty "Sơn Việt Demo Co.", 24 công trình, 126 hạng mục. Mọi tên công
> ty, công trình, thương hiệu, sản phẩm đều là bịa; nếu trùng với tên thật thì chỉ là ngẫu nhiên.

## Dự án này là gì

- **Kho dữ liệu quan hệ** (Postgres, 19 bảng) cho hai nửa của một báo giá thi công: *báo giá* (gói → hạng mục → bước
  thi công, điều khoản, phát sinh) và *dự toán* (hạng mục đó được cấu thành từ vật tư, nhân công, lợi nhuận ra sao).
- **Đường nhập dữ liệu có kiểm tra**: mỗi công trình là một file YAML ([định dạng](docs/data-format.md)); lỗi báo kèm vị
  trí trong file, ghi vào DB trong một transaction (hoặc ghi đủ, hoặc không ghi gì).
- **MCP server với 10 tool chỉ đọc**: so sánh đơn giá, giải thích chênh lệch vật tư/nhân công, so sánh tỷ trọng chi
  phí, tìm báo giá, cộng một tool SQL `SELECT` cho những câu hỏi tool có cấu trúc chưa phủ tới.

## Vì sao có ích

Người làm thầu thường phải trả lời những câu như *"báo giá này đắt hay rẻ so với các công trình đã làm?"*, *"nhân công
chiếm bao nhiêu % và có bất thường không?"*, *"hai hạng mục giống nhau mà sao chênh giá?"*. Trong Excel, đáp án nằm rải
rác ở nhiều sheet (báo giá, định mức vật tư, bảng nhân công) và phải ghép tay.

Ở đây mỗi câu hỏi đó có một tool trả lời bằng số liệu, và agent chỉ việc chọn tool rồi diễn giải bằng tiếng Việt:

| Câu hỏi | Tool MCP |
|---|---|
| Hạng mục này đắt hay rẻ so với các hạng mục tương tự đã báo? | `compare_work_item_price` |
| Vì sao đơn giá hai hạng mục khác nhau: vật tư, nhân công hay lợi nhuận? | `compare_work_item_detail` |
| Nhân công chiếm bao nhiêu % tổng báo giá, so với công trình khác? | `compare_project_cost_breakdown` |
| Chi phí thuê thợ ngoài so với công trình tương tự? | `compare_labor_cost` |
| Tóm tắt một công trình; báo giá mới nhất/cao nhất; tìm hạng mục theo tên hay tag | `get_project_overview`, `find_quotations`, `get_quotation`, `get_work_item`, `search_work_items` |
| Mọi thứ còn lại (chỉ `SELECT`, giới hạn số dòng) | `run_readonly_sql` |

Xem [4 ví dụ hỏi đáp thật](#ví-dụ-hỏi-đáp-thật) bên dưới.

## Cách hoạt động

```mermaid
flowchart LR
    Y["data/sample/*.yaml<br/>(mỗi file = 1 công trình)"] -->|"kiểm tra + ghi 1 transaction"| P[("Postgres<br/>schema quotation")]
    P -->|"role chỉ đọc"| M["MCP server :8002<br/>10 tool"]
    M --> A["Claude / Codex / agent khác"]
    I["API ingest :8000<br/>POST /ingest"] -->|"quyền ghi"| P
```

Hai service tách biệt có chủ đích: chỉ service ingest có quyền ghi; MCP server kết nối bằng role Postgres chỉ đọc
(`default_transaction_read_only`), nên một agent dù cố ghi cũng bị chính DB từ chối.

## Chạy thử

Cần Docker. Chạy một lệnh:

```bash
docker compose up
```

Lệnh này dựng Postgres, tạo schema và role chỉ đọc, nạp 24 công trình mẫu, rồi bật API ingest (cổng 8000) và MCP
server (cổng 8002). Cả hai chỉ lắng nghe trên `127.0.0.1`. Khi log báo hai service đã chạy, thử từ terminal khác
(chỉ cần Python 3, không cần cài thêm gì):

```bash
python3 -m scripts.smoke_mcp
python3 -m scripts.mcp_call find_quotations '{"order_by": "total_amount_desc", "limit": 1}'
python3 -m scripts.mcp_call run_readonly_sql '{"query": "SELECT name FROM quotation.project ORDER BY name LIMIT 5"}'
```

Mật khẩu mặc định (`demo-password`, `demo-readonly`) chỉ dành cho demo trên máy cá nhân; đặt `POSTGRES_PASSWORD` và
`RO_PASSWORD` để đổi, xem `docker-compose.yml`. Dừng và xoá dữ liệu: `docker compose down -v`.

## Nối vào agent của bạn

MCP server dùng transport *streamable HTTP* tại `http://127.0.0.1:8002/mcp`.

**Claude Code:**

```bash
claude mcp add --transport http knowledge-base http://127.0.0.1:8002/mcp
```

**Codex** (thêm vào `~/.codex/config.toml`; cú pháp cấu hình MCP có thể khác theo phiên bản, xem tài liệu của Codex):

```toml
[mcp_servers.knowledge-base]
url = "http://127.0.0.1:8002/mcp"
```

Rồi hỏi bằng tiếng Việt, ví dụ: *"Vì sao đơn giá chống thấm sân thượng ở Biệt thự Sen Vàng cao hơn Biệt thự Lúa Non?"*

## Ví dụ hỏi đáp thật

Bốn ví dụ sau do một agent Claude trả lời bằng cách gọi các tool trên chính bộ dữ liệu `data/sample/`. Số liệu lấy
nguyên từ kết quả tool và đã được đối chiếu với log gọi tool; mỗi trang có lệnh để tự lặp lại.

1. [Đơn giá chống thấm sân thượng của Biệt thự Sen Vàng có đắt so với công trình tương tự?](docs/examples/01-gia-so-voi-cong-trinh-tuong-tu.md)
   Cao hơn trung bình 10,1% (244.814,83 đ so với 222.291,19 đ), nằm trong nhóm cao nhưng chưa phải cao nhất.
2. [Tỷ trọng nhân công của Văn phòng Ngọc Lan có bất thường không?](docs/examples/02-ty-trong-nhan-cong-bat-thuong.md)
   54,50% tổng báo giá, cao hơn trung bình 36,64% và vượt cả mức cao nhất của 22 công trình còn lại có dự toán.
3. [Vì sao Sen Vàng đắt hơn Lúa Non?](docs/examples/03-chenh-lech-do-vat-tu.md)
   Do vật tư: chống thấm PU đàn hồi so với gốc xi măng polymer; nhân công và lợi nhuận gần như bằng nhau.
4. [Vì sao Bạch Dương đắt hơn Liên Hoa?](docs/examples/04-chenh-lech-do-nhan-cong.md)
   Do nhân công: thuê ngoài hoàn toàn so với dùng thợ đội nhà; vật tư còn làm giá Bạch Dương thấp đi một chút.

## Định dạng file báo giá

Một file YAML = một công trình: `project`, `quotation` (gói, hạng mục, bước thi công, điều khoản), `extras` (phát sinh)
và `estimation` (dự toán). Tag (*concept*) của hạng mục lấy từ một danh sách cho phép, nhờ đó bộ so sánh tìm được hạng
mục tương tự mà không cần mô hình ngôn ngữ. Mô tả đầy đủ và các quy tắc kiểm tra: [docs/data-format.md](docs/data-format.md).

```bash
python -m app.cli ingest data/sample          # nhập cả thư mục (cần DATABASE_URL, xem .env.example)
curl -X POST --data-binary @file.yaml -H 'Content-Type: application/x-yaml' http://127.0.0.1:8000/ingest
```

## Dữ liệu giả

`data/sample/` do `scripts/generate_sample_data.py` sinh ra, tất định (cùng seed cho cùng kết quả) và có test bảo đảm
thư mục khớp đầu ra của bộ sinh. Các con số "khớp theo cấu trúc": chọn vài đại lượng gốc (diện tích, giá thùng, số thợ,
định mức) rồi suy ra mọi tổng, nên báo giá, dự toán và cơ cấu chi phí luôn nhất quán.

Bảy công trình *kịch bản* được đặt cố định để các câu hỏi mẫu có đáp án rõ: hai cặp có cùng quy mô nhưng chênh giá chống
thấm do vật tư (Sen Vàng/Lúa Non) hoặc do nhân công thuê ngoài (Bạch Dương/Liên Hoa), một công trình có tỷ trọng nhân
công cao bất thường (Ngọc Lan), một công trình chưa có dự toán, một công trình không có phát sinh và có hạng mục chưa
khai bước thi công. Phần còn lại là ngẫu nhiên có seed. Sinh lại: `python -m scripts.generate_sample_data --out data/sample`.

## Kiến trúc

```
app/domains/quotation/            domain duy nhất: domain/ → application/ → infrastructure/ (19 bảng SQLAlchemy)
  application/services/ingest/    schema YAML, kiểm tra, ánh xạ DTO, ghi một transaction
  application/services/           các bộ so sánh: đơn giá, chi tiết dự toán, nhân công, cơ cấu chi phí
app/core/services/                lớp truy vấn đọc mà MCP dùng
app/interfaces/http/api.py        service ingest (FastAPI): /health, /ingest, /work-items/{id}
main_mcp.py                       MCP server (10 tool, role Postgres chỉ đọc)
scripts/                          sinh dữ liệu, seed, init DB, smoke test, client MCP tối giản
data/sample/                      24 file YAML giả
```

## Phát triển và test

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
createdb knowledge_base_test
export TEST_DATABASE_URL=postgresql+psycopg2://USER:PASS@localhost:5432/knowledge_base_test
export TEST_DATABASE_URL_READONLY=postgresql+psycopg2://knowledge_base_ro:PASS@localhost:5432/knowledge_base_test
.venv/bin/pytest -q
```

Test chạy trên Postgres thật; thiếu hai biến môi trường trên thì dừng ngay với hướng dẫn. Role `knowledge_base_ro`
phải tồn tại sẵn (ví dụ `CREATE ROLE knowledge_base_ro LOGIN PASSWORD 'PASS'`); test tự cấp quyền `SELECT` trên schema test.
Chi tiết quy ước code: [CLAUDE.md](CLAUDE.md). Kiểm tra stack Docker từ đầu đến cuối: `scripts/smoke_compose.sh`.

## Giới hạn và hướng phát triển

- **Chưa có giao diện chat.** Bản này chỉ có MCP server; muốn hỏi đáp thì nối vào Claude/Codex như trên. Dự kiến thêm
  bot terminal hoặc giao diện web đơn giản.
- **Chưa có bộ nhớ hội thoại.** Mỗi câu hỏi độc lập; lịch sử trong phiên do chính agent bạn dùng giữ.
- **Ingest từ chối công trình trùng tên** (409) thay vì ghi đè; `scripts/seed.py` xoá sạch rồi nạp lại.
- Quan hệ giá là phép nhân, `(vật tư + nhân công) × (1 + lợi nhuận) ≈ đơn giá`, nên các khoản chênh không cộng thẳng ra
  mức chênh giá cuối; tool và tài liệu đều nói rõ điều này.
- Dữ liệu không có "hiện trạng công trình", nên không giải thích được chênh giá do yếu tố đó.

## Giấy phép

[MIT](LICENSE).
