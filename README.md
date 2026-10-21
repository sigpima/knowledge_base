# knowledge_base

**Hỏi đáp báo giá thi công sơn bằng agent AI.** Kho dữ liệu báo giá và dự toán trong Postgres, nạp từ file YAML có
cấu trúc, cùng một MCP server chỉ đọc để Claude, Codex hoặc agent khác trả lời kiểu *"vì sao đơn giá hạng mục này ở
công trình A cao hơn công trình B?"* kèm số liệu cụ thể.

> Toàn bộ dữ liệu trong repo là **giả lập**: công ty "Sơn Việt Demo Co.", 24 công trình, 126 hạng mục. Mọi tên công
> ty, công trình, thương hiệu, sản phẩm đều là bịa; nếu trùng với tên thật thì chỉ là ngẫu nhiên.
> Xem [Tuyên bố miễn trừ](#tuyên-bố-miễn-trừ).

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
`RO_PASSWORD` để đổi, xem `docker-compose.yml`. Mỗi lần chạy `docker compose up`, bước seed xoá sạch rồi nạp lại dữ liệu mẫu từ `data/sample`, nên công trình bạn tự nhập qua `/ingest` sẽ mất; muốn giữ, đừng chạy lại seed. Dừng và xoá dữ liệu: `docker compose down -v`.

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

## Chat ngay trong terminal (Gemini)

Không có sẵn Claude/Codex? Dự án có một bot hỏi đáp chạy trong terminal, dùng Gemini làm mô hình và tự gọi 10 tool MCP ở trên.
Phần này **tuỳ chọn**: chỉ bot cần khoá API, mọi thứ còn lại chạy không cần khoá.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-chat.txt
export GEMINI_API_KEY=...        # khoá lấy tại https://aistudio.google.com/apikey (hoặc ghi vào file .env)
docker compose up                # terminal khác: bot nối vào MCP server ở cổng 8002
.venv/bin/python -m app.chat
```

Gõ câu hỏi tiếng Việt rồi Enter. Mỗi lần mô hình gọi một tool, bot in một dòng `↳ tên_tool {tham số}` trước câu trả lời, để
bạn thấy số liệu đến từ đâu (thêm `--quiet` để ẩn). Lệnh trong phiên: `/tools`, `/clear` (xoá ngữ cảnh), `/help`, `/exit`.

- **Trí nhớ:** trong một phiên, bot nhớ các lượt trước nên hỏi tiếp được ("còn công trình kia thì sao?"); `/clear` hoặc mở phiên mới thì quên.
- **Lịch sử:** mỗi phiên được ghi vào một file JSON trong `chat_logs/` (câu hỏi, câu trả lời, các lần gọi tool, thời điểm), chỉ để bạn xem lại;
  bot không đọc lại chúng. Tắt bằng `--no-log`, đổi thư mục bằng `--log-dir` hoặc `CHAT_LOG_DIR`.
- Đổi mô hình bằng `--model` hoặc `GEMINI_CHAT_MODEL`; trỏ tới MCP server khác bằng `--url` hoặc `MCP_SERVER_URL`.

## API chat cho web

Muốn nhúng hộp chat vào website? Service `chat` (`main_chat.py`, cổng 8003) phát câu trả lời dưới dạng **SSE** (Server-Sent Events):
trình duyệt thấy từng lần mô hình gọi tool, rồi câu trả lời. Service này tách khỏi API ingest (có quyền ghi) và chỉ nói chuyện với MCP server chỉ đọc.
Cần `GEMINI_API_KEY`. Trong compose, service này nằm sau *profile* `chat` nên **không** chạy khi bạn gõ `docker compose up` thường
(lệnh đó vẫn chỉ bật db + seed + api + mcp, không cần khoá). Muốn bật thêm API chat, đặt khoá rồi thêm `--profile chat` (hoặc `COMPOSE_PROFILES=chat`):

```bash
export GEMINI_API_KEY=...        # hoặc ghi vào file .env cạnh docker-compose.yml
docker compose --profile chat up --build -d     # hoặc: GEMINI_API_KEY=... docker compose --profile chat up -d
curl localhost:8003/chat/status                      # {"enabled":true}
curl -N -X POST localhost:8003/chat/stream -H 'content-type: application/json' \
  -d '{"message":"Báo giá mới nhất giá bao nhiêu?"}'
```

Dừng cả service chat: `docker compose --profile chat down` (thêm `-v` để xoá dữ liệu); `docker compose down` không kèm profile sẽ để lại container `chat`.

**`POST /chat/stream`**, body JSON `{"message": "...", "session_id": null}`, trả `text/event-stream`. Bỏ trống `session_id` ở lượt đầu;
lấy `session_id` trong sự kiện `start` và gửi lại ở các lượt sau để hỏi tiếp trong cùng một phiên.

| Sự kiện | Dữ liệu (`data`, JSON) |
| --- | --- |
| `start` | `{"session_id"}` |
| `tool_call` | `{"call_id", "tool", "args"}` |
| `tool_result` | `{"call_id", "tool", "ok", "duration_ms", "row_count", "sql", "preview"}` (`sql` chỉ có với `run_readonly_sql`; `preview` bị cắt ngắn) |
| `answer` | `{"text"}` |
| `done` | `{"duration_ms"}` |
| `error` | `{"code": "model" \| "session_full" \| "internal", "message"}`; sau `error` luồng đóng và **không** có `done` |

Một lượt bình thường đi theo thứ tự `start`, tối đa 5 cặp `tool_call`/`tool_result`, `answer`, `done` (lần gọi tool thứ 6 trở đi trong cùng một câu hỏi
bị từ chối, không chạm tới MCP server và không phát sự kiện). Lỗi kiểm tra đầu vào trả JSON thường trước khi tạo phiên hay gọi Gemini, theo thứ tự:
`503 {"code": "demo_disabled"}` (đã tắt), `415 {"code": "unsupported_media_type"}` (thiếu `Content-Type: application/json`),
`413 {"code": "too_long"}` (body quá 16 KB, bị chặn trước khi đọc hết), `422 {"code": "invalid_question"}` (rỗng hoặc sai dạng),
`422 {"code": "too_long"}` (quá `CHAT_MAX_QUESTION_CHARS` ký tự, mặc định 500). **`GET /chat/status`** trả `{"enabled": true|false}` để web ẩn/hiện hộp chat.
Service không phơi `/docs`, `/redoc`, `/openapi.json`.

| Biến môi trường | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `GEMINI_API_KEY` | (bắt buộc) | khoá Gemini; thiếu thì `main_chat.py` không chạy |
| `MCP_SERVER_URL` | `http://127.0.0.1:8002/mcp` | MCP server để gọi tool (trong compose: `http://mcp:8002/mcp`) |
| `CHAT_API_HOST` / `CHAT_API_PORT` | `127.0.0.1` / `8003` | địa chỉ lắng nghe (compose đặt `0.0.0.0` trong container, cổng host chỉ mở trên `127.0.0.1`) |
| `CHAT_DEMO_ENABLED` | `true` | **công tắc tắt**: `false` thì `/chat/status` báo `enabled: false` và `/chat/stream` trả 503; chỉ đọc lúc khởi động, đổi xong phải tạo lại container (`docker compose --profile chat up -d`) |
| `CHAT_MAX_QUESTION_CHARS` | `500` | độ dài tối đa của câu hỏi |
| `CHAT_MAX_TURNS_PER_SESSION` | `30` | số lượt hỏi tối đa của một phiên (quá thì `error` `session_full`) |
| `CHAT_SESSION_TTL_SECONDS` | `1800` | phiên không hoạt động quá thời gian này bị xoá |
| `CHAT_MAX_SESSIONS` | `200` | số phiên đồng thời tối đa |

Lưu ý khi công bố ra internet: phiên chỉ nằm trong RAM của một tiến trình (khởi động lại là mất, không chạy nhiều bản sao), và endpoint web **không lưu câu hỏi của người xem**
(không ghi log, không ghi file; khác với bot terminal ở trên có `chat_logs/`). Đặt sau một reverse proxy có HTTPS, giới hạn tần suất và CORS theo domain của bạn; nhớ tắt buffer
của proxy để SSE chảy liền (service đã gửi `X-Accel-Buffering: no`). Test tự động chạy toàn bộ đường đi bằng Gemini giả; việc gọi Gemini thật cần khoá của bạn và nên tự kiểm tra bằng lệnh `curl` ở trên.

Vận hành:

- Service chat giữ **một** phiên MCP cho cả tiến trình. Compose khởi động lại `chat` mỗi khi `mcp` được khởi động lại qua compose
  (`depends_on` với `restart: true`). Riêng khi container `mcp` tự chết (nó không có chính sách `restart`), phải bật lại cả hai:
  `docker compose --profile chat up -d mcp chat` (hoặc `restart mcp chat`), nếu không mọi lần gọi tool của chat sẽ lỗi.
- Người xem có thể khiến bot chạy SQL chỉ đọc tuỳ ý (qua `run_readonly_sql`), kể cả đọc các view catalog của PostgreSQL. Role dùng ở đây
  chỉ có quyền đọc và bị `statement_timeout` 5 giây, và dữ liệu mẫu là bịa, nên đó là rủi ro chấp nhận được cho bản demo; đừng trỏ service này vào dữ liệu thật.

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

- **Chỉ có bot terminal, chưa có giao diện web.** Bot cần khoá Gemini; bốn ví dụ trong `docs/examples/` được một agent Claude trả lời qua
  chính các tool MCP này (chưa phải qua bot terminal).
- **Trí nhớ chỉ trong phiên.** Bot nhớ các lượt trước trong cùng một lần chạy (hết ngữ cảnh dài thì dùng `/clear`); lịch sử JSON chỉ để
  xem lại, không được nạp lại vào lần chạy sau.
- **Mỗi tên công trình chỉ có một bản.** Gửi lại file y hệt thì bỏ qua (200 `unchanged`), cùng tên nhưng nội dung khác thì 409, muốn thay thế phải yêu cầu rõ (`?on_conflict=replace` / `--replace`); xem [docs/data-format.md](docs/data-format.md). Không giữ lịch sử phiên bản. `scripts/seed.py` thì xoá sạch rồi nạp lại.
- **`run_readonly_sql`** chỉ nhận một câu `SELECT`/`WITH`, trả tối đa 200 dòng (trường `truncated` báo có bị cắt không).
- Quan hệ giá là phép nhân, `(vật tư + nhân công) × (1 + lợi nhuận) ≈ đơn giá`, nên các khoản chênh không cộng thẳng ra
  mức chênh giá cuối; tool và tài liệu đều nói rõ điều này.
- Dữ liệu không có "hiện trạng công trình", nên không giải thích được chênh giá do yếu tố đó.

## Tuyên bố miễn trừ

Mọi thương hiệu và sản phẩm xuất hiện trong repo này, ví dụ **Vietcoat**, **Hoàng Sơn**, **Đại Phát**, **AnTâm** và các dòng sản
phẩm như "AnTâm Seal PU" hay "Vietcoat Weather Plus", cùng công ty "Sơn Việt Demo Co.", tên công trình, địa chỉ, đơn giá và
định mức, đều do tác giả **tự bịa** ra để minh hoạ. Chúng không liên quan, không đại diện, không được tài trợ hay xác nhận bởi bất
kỳ doanh nghiệp, thương hiệu, sản phẩm hay công trình thật nào. Nếu có tên trùng hoặc giống tên thật thì chỉ là ngẫu nhiên, ngoài
ý muốn của tác giả.

Các con số chỉ mang tính minh hoạ cách dự án hoạt động: không phản ánh giá thị trường thật và không nên dùng để báo giá hay ra quyết
định kinh doanh. Nếu bạn là chủ sở hữu một nhãn hiệu và thấy tên nào trùng với nhãn hiệu của mình, hãy mở một issue, tên đó sẽ được đổi.

## Giấy phép

[MIT](LICENSE).
