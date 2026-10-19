"""Kiểm tra giá trị trong file YAML có vừa các cột Postgres sẽ lưu nó không.

Không có bước này thì chuỗi quá dài, số quá lớn hoặc quá nhiều chữ số thập phân chỉ lộ ra lúc ghi DB
(lỗi 500 không kèm vị trí), hoặc tệ hơn là bị Postgres làm tròn âm thầm. Giới hạn lấy thẳng từ các
model SQLAlchemy nên không thể lệch với schema.
"""
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Integer, Numeric, String

from app.domains.quotation.infrastructure.persistence import models as m

from . import schema as s

INT32_MAX = 2**31 - 1

# Lớp mô tả (spec) -> (model lưu nó, {tên trường YAML: tên cột} khi hai tên khác nhau).
SPEC_TO_MODEL: dict[type[BaseModel], tuple[type, dict[str, str]]] = {
    s.ProjectSpec: (m.ProjectModel, {}),
    s.QuotationSpec: (m.QuotationModel, {"code": "quotation_code"}),
    s.PackageSpec: (m.QuotationPackageModel, {}),
    s.WorkItemSpec: (m.WorkItemModel, {}),
    s.ConceptRef: (m.ConceptModel, {}),
    s.StepSpec: (m.WorkStepModel, {"name": "description"}),
    s.ScopeTermSpec: (m.QuotationScopeTermModel, {}),
    s.PaymentTermSpec: (m.QuotationPaymentTermModel, {}),
    s.WarrantySpec: (m.QuotationWarrantyTermModel, {}),
    s.ExtraSpec: (m.ExtraQuotationModel, {}),
    s.TotalDetailSpec: (m.TotalDetailModel, {}),
    s.LaborProcessSpec: (m.LaborInfoProcessModel, {}),
    s.LaborSpec: (m.LaborInfoModel, {}),
    s.MainMaterialSpec: (m.MainMaterialModel, {}),
    s.EstimationItemSpec: (m.EstimationWorkItemModel, {}),
    s.SubMaterialUsageSpec: (m.ItemSubModel, {}),
    s.SubMaterialSpec: (m.SubMaterialModel, {}),
    s.ProductToBuySpec: (m.ProductToBuyModel, {}),
    s.EstimationSpec: (m.EstimationModel, {}),
}

# Trường không có cột cùng tên: khoá cục bộ, tham chiếu hoặc danh sách con (được kiểm tra ở spec của chính chúng).
UNSTORED_FIELDS = {
    ("QuotationSpec", "packages"), ("QuotationSpec", "scope_terms"), ("QuotationSpec", "payment_terms"),
    ("QuotationSpec", "warranty"), ("PackageSpec", "work_items"), ("WorkItemSpec", "key"),
    ("WorkItemSpec", "concepts"), ("WorkItemSpec", "steps"), ("LaborSpec", "processes"),
    ("EstimationItemSpec", "work_item"), ("EstimationItemSpec", "labor"),
    ("EstimationItemSpec", "main_materials"), ("SubMaterialSpec", "usages"),
    ("SubMaterialUsageSpec", "work_item"), ("EstimationSpec", "total_details"),
    ("EstimationSpec", "items"), ("EstimationSpec", "sub_materials"), ("EstimationSpec", "products_to_buy"),
}


def _decimal_shape(value: Decimal) -> tuple[int, int]:
    """(số chữ số phần nguyên, số chữ số thập phân) không đụng tới decimal context, nên an toàn với số mũ khổng lồ."""
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if digits == [0]:
        return 0, 0
    return max(0, len(digits) + exponent), max(0, -exponent)


def _problem(value, column) -> str | None:
    column_type = column.type
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(column_type, String) and isinstance(value, str) and column_type.length:
        if len(value) > column_type.length:
            return f"dài {len(value)} ký tự, cột {column.table.name}.{column.name} chỉ chứa tối đa {column_type.length}"
    elif isinstance(column_type, Numeric) and isinstance(value, (Decimal, int)):
        shape = _decimal_shape(Decimal(value) if isinstance(value, int) else value)
        precision, scale = column_type.precision, column_type.scale or 0
        if shape[1] > scale:
            return f"{value} có quá {scale} chữ số thập phân (cột {column.table.name}.{column.name} sẽ làm tròn)"
        if shape[0] > precision - scale:
            return f"{value} quá lớn: tối đa {precision - scale} chữ số phần nguyên (cột {column.table.name}.{column.name})"
    elif isinstance(column_type, Integer) and isinstance(value, int) and abs(value) > INT32_MAX:
        return f"{value} vượt giới hạn số nguyên ±{INT32_MAX} của cột {column.table.name}.{column.name}"
    return None


def check_column_limits(value, path: str = "") -> list[str]:
    """Duyệt cây spec, trả về danh sách lỗi dạng `"<đường.dẫn>: <thông báo>"`."""
    errors: list[str] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            errors += check_column_limits(item, f"{path}[{index}]")
        return errors
    if not isinstance(value, BaseModel):
        return errors

    mapping = SPEC_TO_MODEL.get(type(value))
    columns = {c.name: c for c in mapping[0].__table__.columns} if mapping else {}
    overrides = mapping[1] if mapping else {}
    for field in type(value).model_fields:
        child = getattr(value, field)
        child_path = f"{path}.{field}" if path else field
        column = columns.get(overrides.get(field, field))
        if column is not None:
            values = child if isinstance(child, list) else [child]
            for index, item in enumerate(values):
                problem = _problem(item, column)
                if problem:
                    errors.append(f"{child_path}{f'[{index}]' if isinstance(child, list) else ''}: {problem}")
        errors += check_column_limits(child, child_path)
    return errors
