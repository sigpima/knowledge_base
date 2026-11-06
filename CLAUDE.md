# CLAUDE.md

Hướng dẫn cho Claude Code (và agent khác) khi làm việc trong repo `knowledge_base`.

## Dự án là gì

Demo công khai: kho dữ liệu báo giá thi công sơn (dữ liệu giả) trong Postgres, nạp từ file YAML có cấu trúc,
và một MCP server chỉ đọc để agent hỏi đáp (so sánh đơn giá, giải thích chênh lệch vật tư/nhân công).
Toàn bộ tên công ty, công trình, sản phẩm đều là bịa. README.md là bản giới thiệu đầy đủ.

## Lệnh thường dùng

```bash
docker compose up                         # Postgres + nạp dữ liệu mẫu + API (8000) + MCP (8002)
python3 -m scripts.smoke_mcp              # kiểm tra MCP đang chạy (11 tool)
python3 -m scripts.mcp_call list          # xem tool; gọi thử: python3 -m scripts.mcp_call TEN_TOOL '{"...": ...}'
python -m scripts.generate_sample_data --out data/sample   # sinh lại dữ liệu mẫu (tất định)
python -m scripts.init_db && python -m scripts.seed data/sample   # cần DATABASE_URL, RO_PASSWORD
python -m app.cli ingest PATH             # nhập file/thư mục YAML (--replace để thay công trình cùng tên)
python -m app.chat                        # bot hỏi đáp trong terminal (cần GEMINI_API_KEY và MCP server đang chạy)
python main_chat.py                       # API chat cho web (SSE, cổng 8003; cần GEMINI_API_KEY và MCP server đang chạy)
GEMINI_API_KEY=... docker compose --profile chat up -d   # thêm service `chat` (127.0.0.1:8003); `docker compose up` thường không bật nó
GEMINI_API_KEY=... docker compose --profile rag up -d    # RAG chính sách: thêm `milvus` + `policy-seed` (nạp data/policies); ghép được với --profile chat
python -m app.cli ingest-policies data/policies --prune   # nạp tài liệu chính sách vào Milvus (cần MILVUS_URI, GEMINI_API_KEY); mã thoát 0/1/2
python -m scripts.eval_retrieval [--top-k 5]   # đo recall/MRR truy xuất chính sách bằng data/policy_eval.yaml (cần GEMINI_API_KEY + Milvus đã nạp); mã thoát 0/2
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
- `app/chat/` – bot terminal tuỳ chọn: `service.py` (Gemini tự gọi tool MCP, nhớ trong phiên), `history.py` (log JSON mỗi phiên, chỉ ghi), `cli.py` (vòng lặp REPL). `requirements-chat.txt` chứa `google-genai`; test e2e dùng SDK thật + server Gemini giả cục bộ nên không cần khoá.
- `app/chat/events.py` (sự kiện SSE + tóm tắt kết quả tool), `app/chat/sessions.py` (`SessionStore`: TTL, giới hạn phiên/lượt, khoá theo phiên); `ChatService.ask_stream` phát sự kiện từng bước.
- `app/interfaces/http/chat_api.py` + `main_chat.py` – API chat cho web: `POST /chat/stream` (SSE: `start`, `tool_call`, `tool_result`, `answer`, `done` | `error`) và `GET /chat/status`, cổng 8003, biến `CHAT_*` (công tắc `CHAT_DEMO_ENABLED`). Không bao giờ lưu câu hỏi của người xem. Image Docker cài `requirements-chat.txt`.
- `app/domains/policy/` – RAG chính sách (tuỳ chọn): `application/services/` (`corpus.py` front matter, `chunker.py`, `ingest.py`, `retrieval.py`), `infrastructure/embedding/` (Gemini), `infrastructure/vectorstore/` (Milvus). Tool `search_policies` dựng lười nên MCP chạy được khi chưa có Milvus/khoá. Xem `docs/rag.md`.
- `main_mcp.py` – MCP server (streamable-http, cổng 8002), đúng 11 tool, kết nối bằng role Postgres **chỉ đọc**.
- `scripts/` – sinh dữ liệu mẫu, seed, init DB, smoke test, client MCP tối giản.
- `data/sample/` – 24 file YAML giả (được commit; phải khớp đầu ra của bộ sinh – có test).
- `data/policy_eval.yaml` + `scripts/eval_retrieval.py` – bộ 28 câu hỏi đánh giá truy xuất chính sách và kịch bản đo (chưa chạy với model embedding thật; xem docs/rag.md).
- `data/policies/` – 12 tài liệu chính sách giả (Markdown + front matter), nguồn của RAG.

## Quy ước

- Tiền/số lượng luôn `Decimal`, không `float`. File YAML đọc số thập phân thành `Decimal` trực tiếp.
- Dataclass cho DTO/entity; Pydantic chỉ cho dữ liệu vào từ ngoài (YAML, HTTP); SQLAlchemy 2.0 `Mapped[...]` cho bảng.
- Caller sở hữu transaction: repository chỉ `flush`, `ingest_quotation` mới `commit`.
- Ingest nhận diện công trình bằng `project.name` (UNIQUE) + `project.content_hash`: cùng nội dung = `unchanged`, khác nội dung = `DuplicateProjectError`/409, `on_conflict="replace"` xoá cây cũ rồi ghi mới trong một transaction. Đổi cột `project` thì DB cũ cần `docker compose down -v` (không có migration).
- `run_readonly_sql`: `app/mcp/sql_guard.py` che chuỗi/chú thích trước khi kiểm tra, luôn bọc câu truy vấn trong `SELECT * FROM (...) LIMIT n`; chốt chặn thật vẫn là role chỉ đọc.
- RAG tuỳ chọn, cần Milvus và khoá Gemini (cả lúc nạp lẫn lúc truy vấn); không có thì `search_policies` trả `{"error": ...}`, các tool khác không bị ảnh hưởng. Trong compose, `mcp` không `depends_on` `policy-seed` (nạp lỗi không được làm sập MCP). Vector gắn với model: đổi `GEMINI_EMBEDDING_MODEL` phải chạy lại `ingest-policies`, và `mcp` phải dùng cùng model.
- Chỉ-đọc của MCP với kho chính sách nằm ở mã (`read_only=True` trong `MilvusPolicyStore`), không phải ở Milvus (demo không xác thực, cổng chỉ mở 127.0.0.1). Test dùng Milvus Lite (fixture `policy_store`/`policy_client` trong `tests/conftest.py`, cần `pip install -r requirements-dev.txt`; tự skip nếu Lite không chạy được) nên không cần Docker hay khoá; embedder giả là `tests/policy_fakes.py`.
- Định danh bằng tiếng Anh/ASCII; chuỗi nghiệp vụ sơn bằng tiếng Việt; tài liệu viết tiếng Việt.
- Schema thay đổi: sửa model trong `app/domains/quotation/infrastructure/persistence/models/` và `metadata/*.yaml`
  (tài liệu cột, không đọc lúc chạy). Không dùng Alembic.
- Các trường `*_diff` của tool so sánh là **B trừ A**.

## Trước khi commit

- Chạy `python scripts/check_scrub.py`: quét từ khoá không được phép (thương hiệu thật, đường dẫn cá nhân, v.v.).
  Ngoài danh sách mặc định, script còn đọc `.scrub-patterns` cục bộ (git bỏ qua file này, không bao giờ commit).
- Không thêm dữ liệu thật, tên thương hiệu thật hay thông tin cá nhân vào repo, kể cả trong test và tài liệu.
