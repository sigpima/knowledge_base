"""Danh mục dữ liệu giả cho bộ sinh file báo giá mẫu.

Mọi tên công ty, thương hiệu, sản phẩm, công trình ở đây đều là bịa. Giá và định mức
được hiệu chỉnh theo mặt bằng thị trường để dữ liệu trông hợp lý, không lấy từ nguồn nào.
"""
from dataclasses import dataclass, field

COMPANY_NAME = "Sơn Việt Demo Co."

BUILDING_TYPES = [
    "Chung cư", "Biệt thự", "Nhà phố", "Văn phòng", "Nhà xưởng",
    "Trường học", "Khách sạn", "Trung tâm thương mại", "Bệnh viện", "Resort", "Showroom",
]
PROJECT_NAMES = [
    "Hoa Mai", "Sen Vàng", "Lúa Non", "Bạch Dương", "Liên Hoa", "Ngọc Lan", "Thành Công",
    "Ánh Sao", "Mặt Trời", "Phù Sa", "Đại Ngàn", "Hải Âu", "Thanh Tùng", "Kim Quy",
    "An Phú", "Bình Minh", "Cửu Long", "Dạ Lan", "Đông Hưng", "Gia Bảo", "Hồng Hà",
    "Khánh Vân", "Lam Sơn", "Minh Châu", "Nam Phong", "Phúc Lộc", "Quế Lâm", "Tây Hồ",
]
STREETS = [
    "Nguyễn Huệ", "Lê Lợi", "Trần Hưng Đạo", "Hai Bà Trưng", "Điện Biên Phủ", "Nguyễn Văn Linh",
    "Phạm Văn Đồng", "Võ Văn Kiệt", "Lý Thường Kiệt", "Hoàng Văn Thụ", "Nguyễn Trãi",
    "Trường Chinh", "Quang Trung", "Lê Văn Việt", "Phan Xích Long",
]
PLACES = [
    "Quận 1, TP.HCM", "Quận 2, TP.HCM", "Quận 7, TP.HCM", "Bình Thạnh, TP.HCM", "Gò Vấp, TP.HCM",
    "TP. Thủ Đức, TP.HCM", "TP. Biên Hòa, Đồng Nai", "TP. Vũng Tàu", "TP. Đà Nẵng",
    "TP. Nha Trang, Khánh Hòa", "TP. Cần Thơ", "TP. Hải Phòng", "Bình Dương", "TP. Huế",
]

# Quy trình thi công theo nhóm hạng mục, theo đúng thứ tự thực tế; hai bước cuối là bước bắt buộc.
PROCESS_POOLS = {
    "paint": ["Vệ sinh bề mặt", "Xử lý khuyết tật bề mặt", "Sơn lót", "Sơn phủ lớp 1", "Sơn phủ lớp 2"],
    "putty": ["Vệ sinh bề mặt", "Xử lý khuyết tật bề mặt", "Bả matit lớp 1", "Bả matit lớp 2"],
    "waterproof": ["Vệ sinh bề mặt", "Xử lý bề mặt", "Chống thấm lớp 1", "Chống thấm lớp 2"],
    "metal": ["Vệ sinh bề mặt", "Chà nhám", "Sơn lót chống gỉ", "Sơn phủ"],
}
PROCESS_KIND = {
    "Bả matit hoàn thiện": "putty",
    "Chống thấm sân thượng": "waterproof",
    "Chống thấm nhà vệ sinh": "waterproof",
    "Chống thấm tường ngoài": "waterproof",
    "Sơn dầu cửa sắt lan can": "metal",
    "Sơn chống nóng mái tôn": "metal",
}
# Bước chuẩn bị bề mặt: không dùng sản phẩm, không có số lớp.
PREP_STEPS = {"Vệ sinh bề mặt", "Xử lý khuyết tật bề mặt", "Xử lý bề mặt", "Chà nhám"}

SUB_MATERIAL_CATALOG = [
    ("CCDC", "Rulo sơn", "cái"),
    ("CCDC", "Cọ sơn", "cái"),
    ("vật tư phụ", "Băng keo giấy", "cuộn"),
    ("vật tư phụ", "Bạt che phủ", "m2"),
    ("chi phí vận hành", "Giàn giáo thi công", "bộ"),
    ("chi phí quản lý", "Chi phí giám sát công trình", "tháng"),
    ("chi phí vận chuyển", "Vận chuyển vật tư", "chuyến"),
]

PAYMENT_TRIGGERS = [
    ("DEPOSIT", "Đặt cọc ký hợp đồng"),
    ("MIDTERM", "Nghiệm thu giai đoạn 1"),
    ("MIDTERM2", "Nghiệm thu giai đoạn 2"),
    ("FINAL", "Nghiệm thu bàn giao hoàn công"),
]

SCOPE_ENTRIES = [
    ("bao gồm", "INCLUDE", "Vật tư sơn chính hãng theo bảng báo giá"),
    ("bao gồm", "INCLUDE", "Nhân công thi công đúng quy trình kỹ thuật"),
    ("loại trừ", "EXCLUDE", "Chi phí sửa chữa, cải tạo phát sinh kết cấu"),
    ("loại trừ", "EXCLUDE", "Chi phí xin phép thi công (nếu có)"),
]


@dataclass(frozen=True)
class CatalogItem:
    """Một loại hạng mục: định mức vật tư theo lớp và giá thùng theo phân khúc (VND)."""

    name: str
    unit: str
    area: tuple[int, int]
    tags: tuple[tuple[str, str], ...]
    products: tuple[tuple[str, str, str], ...]  # (phân khúc, dòng sản phẩm, tên sản phẩm)
    coverage: tuple[float, float]  # m2 phủ được trên 1 lít cho 1 lớp, trước hao hụt
    box_liters: tuple[int, ...]
    box_price: dict[str, tuple[int, int]]  # phân khúc -> khoảng giá 1 thùng
    layers: tuple[int, ...] = (2,)
    labor_intensity: float = 1.0
    extra: dict = field(default_factory=dict)


MID, HIGH = "TRUNG CẤP", "CAO CẤP"

WORK_ITEM_CATALOG: list[CatalogItem] = [
    CatalogItem(
        "Sơn nước ngoại thất", "m2", (200, 1500),
        (("category", "Ngoại thất"), ("application", "Tường"), ("effect", "Trang trí")),
        ((MID, "Vietcoat Weather", "Vietcoat Weather ngoại thất"),
         (HIGH, "Vietcoat Weather Plus", "Vietcoat Weather Plus ngoại thất")),
        (9, 12), (18,), {MID: (1_400_000, 1_900_000), HIGH: (2_800_000, 3_800_000)},
    ),
    CatalogItem(
        "Sơn nước nội thất", "m2", (150, 1200),
        (("category", "Nội thất"), ("application", "Tường"), ("effect", "Trang trí")),
        ((MID, "Hoàng Sơn Home", "Hoàng Sơn Home nội thất"),
         (HIGH, "Hoàng Sơn Home Plus", "Hoàng Sơn Home Plus nội thất")),
        (10, 13), (18,), {MID: (1_100_000, 1_500_000), HIGH: (2_200_000, 3_000_000)},
    ),
    CatalogItem(
        "Bả matit hoàn thiện", "m2", (150, 1200),
        (("category", "Nội thất"), ("application", "Tường"), ("stage", "Hoàn thiện")),
        ((MID, "Đại Phát Putty", "Bột bả Đại Phát nội ngoại thất"),
         (HIGH, "Đại Phát Putty Pro", "Bột bả Đại Phát Pro")),
        (1.2, 1.6), (40,), {MID: (380_000, 480_000), HIGH: (520_000, 680_000)},
    ),
    CatalogItem(
        "Chống thấm sân thượng", "m2", (50, 400),
        (("effect", "Chống thấm"), ("application", "Sàn"), ("category", "Ngoại thất")),
        ((MID, "AnTâm Seal", "AnTâm Seal gốc xi măng polymer"),
         (HIGH, "AnTâm Seal PU", "AnTâm Seal PU đàn hồi")),
        (0.9, 1.3), (20,), {MID: (750_000, 1_000_000), HIGH: (1_900_000, 2_500_000)},
        labor_intensity=1.2,
    ),
    CatalogItem(
        "Chống thấm nhà vệ sinh", "m2", (10, 80),
        (("effect", "Chống thấm"), ("application", "Sàn"), ("category", "Nội thất")),
        ((MID, "AnTâm Seal", "AnTâm Seal gốc xi măng polymer"),
         (HIGH, "AnTâm Seal PU", "AnTâm Seal PU đàn hồi")),
        (0.9, 1.3), (20,), {MID: (750_000, 1_000_000), HIGH: (1_900_000, 2_500_000)},
        labor_intensity=1.4,
    ),
    CatalogItem(
        "Sơn epoxy sàn tầng hầm", "m2", (200, 2000),
        (("application", "Sàn"), ("effect", "Bảo vệ"), ("object", "Nhà xưởng")),
        ((MID, "Hoàng Sơn Epoxy", "Hoàng Sơn Epoxy sàn 2 thành phần"),
         (HIGH, "Hoàng Sơn Epoxy Pro", "Hoàng Sơn Epoxy Pro chịu tải")),
        (4, 6), (20,), {MID: (2_400_000, 3_200_000), HIGH: (3_800_000, 5_000_000)},
    ),
    CatalogItem(
        "Sơn lót chống kiềm", "m2", (150, 1200),
        (("application", "Tường"), ("effect", "Bảo vệ"), ("stage", "Hoàn thiện")),
        ((MID, "Vietcoat Primer", "Vietcoat Primer chống kiềm"),
         (HIGH, "Vietcoat Primer Plus", "Vietcoat Primer Plus chống kiềm")),
        (10, 13), (18,), {MID: (1_500_000, 2_000_000), HIGH: (2_400_000, 3_100_000)}, layers=(1,),
    ),
    CatalogItem(
        "Sơn dầu cửa sắt lan can", "m2", (20, 150),
        (("application", "Kim loại"), ("effect", "Bảo vệ")),
        ((MID, "Đại Phát Alkyd", "Sơn dầu Đại Phát Alkyd"),
         (HIGH, "Đại Phát Alkyd Pro", "Sơn dầu Đại Phát Alkyd Pro")),
        (8, 11), (5,), {MID: (380_000, 520_000), HIGH: (600_000, 800_000)},
        labor_intensity=1.3,
    ),
    CatalogItem(
        "Chống thấm tường ngoài", "m2", (100, 900),
        (("effect", "Chống thấm"), ("application", "Tường"), ("category", "Ngoại thất")),
        ((MID, "AnTâm Wall", "AnTâm Wall chống thấm màu"),
         (HIGH, "AnTâm Wall Pro", "AnTâm Wall Pro đàn hồi")),
        (1.5, 2.2), (18,), {MID: (600_000, 800_000), HIGH: (1_400_000, 1_900_000)},
    ),
    CatalogItem(
        "Sơn hiệu ứng đá trang trí", "m2", (30, 300),
        (("category", "Ngoại thất"), ("application", "Tường"), ("effect", "Trang trí")),
        ((MID, "Hoàng Sơn Stone", "Hoàng Sơn Stone giả đá"),
         (HIGH, "Hoàng Sơn Stone Art", "Hoàng Sơn Stone Art nghệ thuật")),
        (1.5, 2.5), (20,), {MID: (2_200_000, 3_000_000), HIGH: (4_000_000, 5_500_000)},
        labor_intensity=1.5,
    ),
    CatalogItem(
        "Sơn chống nóng mái tôn", "m2", (100, 1500),
        (("application", "Kim loại"), ("effect", "Chống nóng"), ("category", "Ngoại thất")),
        ((MID, "Vietcoat Cool", "Vietcoat Cool chống nóng"),
         (HIGH, "Vietcoat Cool Plus", "Vietcoat Cool Plus phản xạ nhiệt")),
        (3, 4.5), (18,), {MID: (1_800_000, 2_400_000), HIGH: (3_000_000, 4_000_000)},
    ),
    CatalogItem(
        "Sơn trần thạch cao", "m2", (100, 800),
        (("category", "Nội thất"), ("application", "Trần"), ("effect", "Trang trí")),
        ((MID, "Hoàng Sơn Ceiling", "Hoàng Sơn Ceiling siêu trắng"),
         (HIGH, "Hoàng Sơn Ceiling Plus", "Hoàng Sơn Ceiling Plus")),
        (11, 14), (18,), {MID: (1_000_000, 1_400_000), HIGH: (1_800_000, 2_400_000)},
    ),
]
