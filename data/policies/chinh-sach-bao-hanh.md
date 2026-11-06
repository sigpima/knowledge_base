---
slug: chinh-sach-bao-hanh
title: Chính sách bảo hành công trình sơn
doc_type: warranty
applies_to:
  - Sơn nước ngoại thất
  - Sơn nước nội thất
  - Bả matit hoàn thiện
  - Chống thấm sân thượng
  - Chống thấm nhà vệ sinh
  - Sơn epoxy sàn tầng hầm
  - Sơn lót chống kiềm
  - Sơn dầu cửa sắt lan can
  - Chống thấm tường ngoài
  - Sơn hiệu ứng đá trang trí
  - Sơn chống nóng mái tôn
  - Sơn trần thạch cao
---

# Chính sách bảo hành công trình sơn

Tài liệu giả lập cho bản demo; công ty, sản phẩm đều là bịa.

Tài liệu này là quy định nội bộ của Sơn Việt Demo Co. về thời hạn bảo hành, gia hạn, khoản giữ lại và ngày bắt đầu bảo hành. Tài liệu trả lời hai câu hỏi thường gặp: công trình được bảo hành bao lâu, và vì sao hai báo giá ghi thời hạn khác nhau. Lỗi nào được bảo hành nằm ở tài liệu loại trừ bảo hành.

## Nguyên tắc: báo giá ghi riêng thì ưu tiên

Thời hạn bảo hành thực tế là thời hạn ghi trong phần bảo hành của báo giá đã ký; mức tiêu chuẩn ở mục sau chỉ dùng để lập báo giá.

1. Nếu báo giá ghi một thời hạn riêng, cao hay thấp hơn mức tiêu chuẩn, thì thời hạn trong báo giá được ưu tiên. Mỗi báo giá chỉ ghi một thời hạn chung cho cả công trình.
2. Nếu báo giá không có phần bảo hành thì mức tiêu chuẩn không tự động áp dụng; hai bên phải thỏa thuận bằng văn bản trước khi ký.
3. Nếu báo giá gộp nhiều nhóm có thời hạn tiêu chuẩn khác nhau (ví dụ sơn nước nội thất 12 tháng, chống thấm 36 tháng) mà không nêu thời hạn chung, cả công trình dùng thời hạn tiêu chuẩn dài nhất trong các nhóm đó.

Lý do: báo giá là văn bản hai bên đã ký, còn bảng tiêu chuẩn là quy định nội bộ mà chủ đầu tư có thể chưa đọc; khi mâu thuẫn, văn bản đã ký phải thắng. Với báo giá gộp, thời hạn chung không được thấp hơn mức tiêu chuẩn của nhóm nào, kẻo nhóm dài nhất bị bảo hành thiếu. Thời hạn dài hơn thường đi kèm giá cao hơn vì chi phí bảo hành tính sẵn vào giá, nên khi so sánh hai báo giá cần xem cả thời hạn bảo hành chứ không chỉ đơn giá.

## Thời hạn tiêu chuẩn theo nhóm hạng mục

Thời hạn tiêu chuẩn phụ thuộc nhóm hạng mục và hệ vật liệu (trung cấp hoặc cao cấp).

1. Sơn trang trí nội thất (sơn nước nội thất, sơn trần thạch cao, bả matit, sơn lót chống kiềm): 12 tháng với hệ trung cấp, 18 tháng với hệ cao cấp.
2. Sơn ngoại thất (sơn nước ngoại thất, sơn hiệu ứng đá trang trí), sơn dầu cửa sắt lan can và sơn chống nóng mái tôn: 24 tháng.
3. Chống thấm (sân thượng, nhà vệ sinh, tường ngoài) và sơn epoxy sàn tầng hầm: 36 tháng với hệ cao cấp, 24 tháng với hệ trung cấp.

Lý do: thời hạn bảo hành phản ánh thời gian cần để lỗi thi công lộ ra. Lỗi nội thất như bong tróc, phồng rộp thường xuất hiện trong năm đầu nên 12 đến 18 tháng là đủ. Ngoại thất chịu hai mùa nắng mưa nên cần 24 tháng. Chống thấm có lỗi chỉ lộ ra sau vài mùa mưa nên hệ cao cấp được 36 tháng; hệ trung cấp gốc xi măng polymer tạo màng cứng, kém co giãn hơn hệ PU đàn hồi, nên chỉ 24 tháng.

## Gia hạn bảo hành

Phần bảo hành của báo giá có hai trường `extend_percent` và `extend_period` để bán thêm gia hạn.

Đây là quy ước của bản demo, vì mô tả cột trong dữ liệu không nói rõ: `extend_percent` là tỉ lệ phần trăm trên giá trị hợp đồng mà chủ đầu tư trả thêm để mua thêm `extend_period` tháng bảo hành. Giá trị 0 nghĩa là không bán gia hạn.

1. `extend_percent` nhận 0, 5 hoặc 10; `extend_period` nhận 0, 3 hoặc 6 tháng.
2. Ví dụ: hợp đồng 1.000.000.000 VND, `extend_percent` bằng 5, `extend_period` bằng 6 thì chủ đầu tư trả thêm 50.000.000 VND để được bảo hành thêm 6 tháng sau thời hạn chính.
3. Nếu một trong hai giá trị bằng 0 thì không có gia hạn và không phát sinh khoản trả thêm.

Lý do: chi phí bảo hành trong cơ cấu chi phí chỉ khoảng 1 đến 2% tổng vật tư, vật tư phụ và nhân công cho thời hạn chính. Gia hạn là cam kết thêm rủi ro nên bên mua trả thêm.

## Giữ lại bảo hành

Chúng ta giữ lại 5% giá trị hợp đồng làm khoản bảo hành, hoàn trả khi hết thời hạn bảo hành chính.

1. Khoản 5% không phải đợt thanh toán riêng; nó được trừ khỏi các đợt thanh toán và hoàn trả ở cuối.
2. Khoản này giữ đến hết thời hạn chính ghi trong báo giá, không kéo dài theo phần gia hạn đã mua.
3. Nếu lỗi thuộc diện bảo hành không được khắc phục đúng hạn, chủ đầu tư có quyền dùng khoản này thuê bên khác sửa.

Lý do: khoản giữ lại bảo đảm chúng ta vẫn có động lực quay lại sửa lỗi sau khi đã nhận gần hết tiền. Phần gia hạn không kéo dài việc giữ tiền vì chủ đầu tư đã trả thêm cho phần đó.

## Bảo hành bắt đầu từ khi nào

Thời hạn bảo hành tính từ ngày ký biên bản nghiệm thu bàn giao hoàn công, không tính từ ngày ký hợp đồng hay ngày xong từng hạng mục.

1. Ngày ghi trên biên bản là ngày bắt đầu; ngày kết thúc là ngày đó cộng số tháng ghi trong báo giá.
2. Nghiệm thu giai đoạn 1 và giai đoạn 2 chỉ là mốc thanh toán và kiểm soát chất lượng, không làm bảo hành bắt đầu chạy.

Lý do: trước bàn giao, công trình còn trong tay chúng ta nên mọi lỗi đều phải sửa không điều kiện; bảo hành chỉ có nghĩa sau khi chủ đầu tư nhận công trình để sử dụng.
