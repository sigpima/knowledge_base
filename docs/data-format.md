# Định dạng file báo giá (YAML)

Mỗi file mô tả **một công trình** gồm báo giá, phát sinh và (tuỳ chọn) dự toán. Ingest đọc file này, kiểm tra,
rồi ghi vào Postgres trong một transaction: hoặc ghi đủ cả công trình, hoặc không ghi gì.

Ví dụ đầy đủ nằm ở [`data/sample/`](../data/sample/) (24 file) và ví dụ nhỏ ở
[`tests/fixtures/valid_minimal.yaml`](../tests/fixtures/valid_minimal.yaml).

## Các khối cấp cao nhất

| Khoá | Bắt buộc | Ý nghĩa |
|---|---|---|
| `project` | có | Thông tin công trình: `name` (duy nhất trong DB), `address`, `estimated_workdays` (danh sách số ngày theo giai đoạn) |
| `quotation` | có | Báo giá: `code`, `issue_date`, `currency` (mặc định `VND`), `total_amount`, `packages`, điều khoản |
| `extras` | không | Danh sách hạng mục phát sinh gắn thẳng vào công trình |
| `estimation` | không | Dự toán: tổng hợp chi phí, chi tiết từng hạng mục, vật tư phụ, sản phẩm cần mua |

Khoá lạ ở bất kỳ cấp nào bị từ chối, kèm vị trí, ví dụ `project.colour: Extra inputs are not permitted`.

## Báo giá (`quotation`)

```yaml
quotation:
  code: BG-2026-001
  issue_date: 2026-03-21
  total_amount: 72800000        # tuỳ chọn; vắng thì tự tính, có thì phải khớp tổng quantity * unit_price (lệch tối đa 1 đồng)
  packages:
    - name: Gói sơn ngoại thất
      work_items:
        - key: ngoai-that-tuong      # khoá cục bộ trong file, duy nhất; dự toán tham chiếu bằng khoá này
          name: Sơn nước ngoại thất
          unit: m2
          quantity: 500
          unit_price: 102000
          concepts:                  # tag để tìm hạng mục tương tự, lấy từ danh sách cho phép bên dưới
            - {type: category, name: Ngoại thất}
          steps:                     # tuỳ chọn; một hạng mục có thể chưa khai bước thi công
            - {name: Sơn lót, product_name: Vietcoat Primer-1, layers: 1}
  scope_terms:                       # phạm vi: bao gồm / loại trừ
    - {scope_type: bao gồm, term_type: INCLUDE, description: Vật tư sơn theo bảng báo giá}
  payment_terms:
    - {percentage: 30, trigger_type: DEPOSIT, trigger_description: Đặt cọc ký hợp đồng}
  warranty: {period: 24, period_unit: tháng, extend_percent: 0, extend_period: 0}
```

Giới hạn theo cột DB: `scope_type` ≤ 20 ký tự, `term_type` và `trigger_type` và `period_unit` ≤ 10 ký tự,
`description`/`trigger_description` ≤ 255 ký tự. Mọi trường của `payment_terms` và `warranty` là bắt buộc.

### Concept (tag) được phép

| `type` | Giá trị `name` |
|---|---|
| `stage` | Thi công thô, Hoàn thiện, Bảo trì |
| `category` | Nội thất, Ngoại thất |
| `application` | Tường, Sàn, Trần, Kim loại |
| `effect` | Chống thấm, Trang trí, Bảo vệ, Chống nóng |
| `object` | Nhà ở, Văn phòng, Nhà xưởng, Công trình công cộng |

Giá trị ngoài bảng này là lỗi; một hạng mục không được lặp cùng một concept và chỉ có tối đa một concept `category`. Danh sách nằm ở `app/domains/quotation/application/services/ingest/concepts.py`.

## Dự toán (`estimation`)

Dự toán cho biết đơn giá của mỗi hạng mục được cấu thành từ đâu. Mỗi mục trong `items` trỏ về một hạng mục báo giá
bằng `work_item: <key>`.

```yaml
estimation:
  total_price: 79500000
  total_details:                 # cơ cấu chi phí: vật tư chính, vật tư phụ, nhân công, lợi nhuận...
    - {type: nhân công, name: Nhân công, price: 20000000}
  items:
    - name: Sơn nước ngoại thất
      work_item: ngoai-that-tuong
      material_unit_price: 60000
      labor_unit_price: 25000
      profit_margin: 0.2         # tỉ lệ, 0.2 = 20%
      labor:
        kn_manday: 20            # ngày công thợ nhà (KN)
        main_out_manday: 10      # ngày công thợ chính thuê ngoài
        sub_out_manday: 5        # ngày công thợ phụ thuê ngoài
        processes:
          - {name: Sơn phủ, days: 4, kn_manday: 16, main_out_manday: 8, sub_out_manday: 4}
      main_materials:
        - {product_name: Vietcoat Top-2, layers: 2, box_price: 1800000, unit_price_per_m2: 36000}
  sub_materials:
    - type: vật tư phụ
      name: Băng keo giấy
      usages:
        - {work_item: ngoai-that-tuong, amount: 20, total_price: 300000}
  products_to_buy: []
```

Quan hệ giá là **phép nhân**, không phải phép cộng:

```
(material_unit_price + labor_unit_price) * (1 + profit_margin)  ≈  unit_price của hạng mục báo giá
```

Loader từ chối mục dự toán nào lệch quá 0,5% so với `unit_price` của hạng mục mà nó trỏ tới.

## Quy tắc kiểm tra

- `work_item.key` duy nhất trong file; tham chiếu `work_item` trong dự toán và vật tư phụ phải trỏ tới key có thật.
- Số tiền và số lượng là **số thập phân chính xác** (`1234567.89` vào DB đúng như vậy, không qua số thực).
- Giá trị phải vừa cột DB sẽ lưu nó: chuỗi không dài quá cột (ví dụ `unit` ≤ 20 ký tự, tên ≤ 255), số không quá số chữ số phần nguyên, và **không nhiều chữ số thập phân hơn cột** (`unit_price: 95000.123` bị từ chối thay vì bị làm tròn âm thầm). `percent_usage` và `construction_loss` là tỉ lệ (0.8 = 80%), không viết 80 hay 100.
- Mỗi hạng mục báo giá chỉ có một dòng dự toán (`estimation.items[*].work_item` không được lặp).
- Khoá lặp trong cùng một mapping YAML bị từ chối (tránh giá trị sau ghi đè âm thầm).
- `extras[*].metadata` là JSON phẳng gồm chuỗi, số nguyên, true/false hoặc null (không dùng số thập phân hay mapping lồng).
- Chuỗi Unicode được chuẩn hoá NFC; BOM đầu file được bỏ qua.
- Không dùng alias YAML (`*x`), không lồng quá sâu, chỉ `safe_load`: file độc hại bị từ chối với lỗi 422, không làm sập server.
- Số viết dạng `1:30` bị từ chối: YAML 1.1 đọc nó là số hệ 60 (= 90) chứ không phải chuỗi. Đặt trong dấu nháy nếu là chữ.

## Gửi lại hoặc sửa một công trình

Công trình được nhận diện bằng `project.name` (duy nhất, DB có ràng buộc `UNIQUE`). Mỗi lần ingest, nội dung file được
chuẩn hoá (không phụ thuộc thứ tự khoá, khoảng trắng, hay `95000` so với `95000.00`) rồi băm sha256 thành `project.content_hash`:

| Tình huống | Kết quả |
|---|---|
| Chưa có công trình tên đó | Ghi mới. HTTP `201`, `"status": "created"` |
| Có rồi, **cùng** nội dung | Không ghi gì. HTTP `200`, `"status": "unchanged"`; gửi lại file cũ (hoặc thử lại sau lỗi mạng) là an toàn |
| Có rồi, nội dung **khác** | Từ chối. HTTP `409` kèm gợi ý; CLI báo lỗi |
| Như dòng trên, kèm `?on_conflict=replace` (HTTP) hoặc `--replace` (CLI) | Xoá toàn bộ cây dữ liệu cũ và ghi cây mới trong **cùng một transaction**. HTTP `200`, `"status": "replaced"`; nếu ghi mới lỗi thì dữ liệu cũ còn nguyên |

Hai request cùng tên gửi đồng thời không thể cùng thành công: request đến sau bị ràng buộc `UNIQUE` chặn, rồi được xử lý như bảng trên
(cùng nội dung thì `unchanged`, khác nội dung thì `409`). Hệ thống không giữ nhiều phiên bản của một công trình.

## Cách nhập

```bash
# Dòng lệnh: một hoặc nhiều file, hoặc cả thư mục
python -m app.cli ingest data/sample
python -m app.cli ingest --replace cong-trinh-da-sua.yaml    # thay thế công trình cùng tên

# HTTP (service ingest, cổng 8000)
curl -X POST --data-binary @file.yaml -H 'Content-Type: application/x-yaml' \
     'http://127.0.0.1:8000/ingest?source_file=file.yaml'          # thêm &on_conflict=replace để thay thế
```

Body phải có `Content-Type` là `application/x-yaml`, `application/yaml` hoặc `text/yaml` (nếu không: `415`). Lỗi kiểm tra trả về `422` với `{"errors": ["quotation.packages[0].work_items[1].key: ...", ...]}`.
