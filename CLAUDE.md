# CLAUDE.md

Hướng dẫn cho Claude Code (và agent khác) khi làm việc trong repo `knowledge_base`.

## Dự án là gì

Demo công khai: kho dữ liệu báo giá thi công sơn (dữ liệu giả) trong Postgres, nạp từ file YAML có cấu trúc,
và một MCP server chỉ đọc để agent hỏi đáp (so sánh đơn giá, giải thích chênh lệch vật tư/nhân công).
Toàn bộ tên công ty, công trình, sản phẩm đều là bịa. README.md là bản giới thiệu đầy đủ.

## Lệnh thường dùng

```bash
docker compose up                         # Postgres + nạp dữ liệu mẫu + API (8000) + MCP (8002)
python3 -m scripts.smoke_mcp              # kiểm tra MCP đang chạy (10 tool)
python3 -m scripts.mcp_call list          # xem tool; gọi thử: python3 -m scripts.mcp_call TEN_TOOL '{"...": ...}'
python -m scripts.generate_sample_data --out data/sample   # sinh lại dữ liệu mẫu (tất định)
python -m scripts.init_db && python -m scripts.seed data/sample   # cần DATABASE_URL, RO_PASSWORD
python -m app.cli ingest PATH             # nhập file/thư mục YAML
```

Test (Postgres thật, bắt buộc đặt biến môi trường, không có giá trị mặc định):

```bash
createdb knowledge_base_test
export TEST_DATABASE_URL=postgresql+psycopg2://USER:PASS@localhost:5432/knowledge_base_test
export TEST_DATABASE_URL_READONLY=postgresql+psycopg2://knowledge_base_ro:PASS@localhost:5432/knowledge_base_test
pytest -q
```

Role `knowledge_base_ro` phải tồn tại sẵn trên Postgres test (tạo bằng `RO_PASSWORD=... python -m scripts.init_db`
trên DB nào đó, hoặc `CREATE ROLE knowledge_base_ro LOGIN PASSWORD '...'`); conftest tự cấp quyền SELECT trên schema test.

## Cấu trúc

- `app/domains/quotation/` – domain duy nhất: `domain/` → `application/` → `infrastructure/` (SQLAlchemy, 19 bảng schema `quotation`).
  - `application/services/ingest/` – schema YAML (`schema.py`), kiểm tra (`loader.py`), ánh xạ DTO (`mapper.py`), ghi một transaction (`writer.py`).
  - `application/services/*_service.py` – các bộ so sánh (đơn giá, chi tiết dự toán, nhân công, cơ cấu chi phí).
- `app/core/services/knowledge_service.py` – lớp truy vấn đọc, MCP dùng với session chỉ đọc.
- `app/interfaces/http/api.py` – service ingest (FastAPI): `/health`, `/ingest`, `/work-items/{id}`.
- `main_mcp.py` – MCP server (streamable-http, cổng 8002), đúng 10 tool, kết nối bằng role Postgres **chỉ đọc**.
- `scripts/` – sinh dữ liệu mẫu, seed, init DB, smoke test, client MCP tối giản.
- `data/sample/` – 24 file YAML giả (được commit; phải khớp đầu ra của bộ sinh – có test).

## Quy ước

- Tiền/số lượng luôn `Decimal`, không `float`. File YAML đọc số thập phân thành `Decimal` trực tiếp.
- Dataclass cho DTO/entity; Pydantic chỉ cho dữ liệu vào từ ngoài (YAML, HTTP); SQLAlchemy 2.0 `Mapped[...]` cho bảng.
- Caller sở hữu transaction: repository chỉ `flush`, `ingest_quotation` mới `commit`.
- Ingest nhận diện công trình bằng `project.name` (UNIQUE) + `project.content_hash`: cùng nội dung = `unchanged`, khác nội dung = `DuplicateProjectError`/409, `on_conflict="replace"` xoá cây cũ rồi ghi mới trong một transaction. Đổi cột `project` thì DB cũ cần `docker compose down -v` (không có migration).
- `run_readonly_sql`: `app/mcp/sql_guard.py` che chuỗi/chú thích trước khi kiểm tra, luôn bọc câu truy vấn trong `SELECT * FROM (...) LIMIT n`; chốt chặn thật vẫn là role chỉ đọc.
- Định danh bằng tiếng Anh/ASCII; chuỗi nghiệp vụ sơn bằng tiếng Việt; tài liệu viết tiếng Việt.
- Schema thay đổi: sửa model trong `app/domains/quotation/infrastructure/persistence/models/` và `metadata/*.yaml`
  (tài liệu cột, không đọc lúc chạy). Không dùng Alembic.
- Các trường `*_diff` của tool so sánh là **B trừ A**.

## Trước khi commit

- Chạy `python scripts/check_scrub.py`: quét từ khoá không được phép (thương hiệu thật, đường dẫn cá nhân, v.v.).
  Ngoài danh sách mặc định, script còn đọc `.scrub-patterns` cục bộ (git bỏ qua file này, không bao giờ commit).
- Không thêm dữ liệu thật, tên thương hiệu thật hay thông tin cá nhân vào repo, kể cả trong test và tài liệu.
