"""Danh sách concept (tag) được phép khai báo trong file YAML báo giá.

Concept gắn nhãn cho từng hạng mục để bộ so sánh tìm được hạng mục tương tự.
"""

CONCEPT_VOCABULARY: dict[str, frozenset[str]] = {
    "stage": frozenset({"Thi công thô", "Hoàn thiện", "Bảo trì"}),
    "category": frozenset({"Nội thất", "Ngoại thất"}),
    "application": frozenset({"Tường", "Sàn", "Trần", "Kim loại"}),
    "effect": frozenset({"Chống thấm", "Trang trí", "Bảo vệ", "Chống nóng"}),
    "object": frozenset({"Nhà ở", "Văn phòng", "Nhà xưởng", "Công trình công cộng"}),
}
