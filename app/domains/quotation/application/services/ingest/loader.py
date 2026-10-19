"""Đọc và kiểm tra file YAML báo giá; lỗi nêu rõ vị trí trong file."""
import unicodedata
from collections.abc import Hashable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .column_limits import check_column_limits
from .concepts import CONCEPT_VOCABULARY
from .schema import QuotationFile

TOTAL_AMOUNT_TOLERANCE = Decimal("1")
COST_RELATION_TOLERANCE = Decimal("0.005")


class QuotationFileError(ValueError):
    """File báo giá không hợp lệ; `errors` có dạng `"<đường.dẫn[0].trong.file>: <thông báo>"`."""

    def __init__(self, errors: list[str], source_name: str = ""):
        self.errors = errors
        self.source_name = source_name
        prefix = f"{source_name}: " if source_name else ""
        super().__init__(prefix + "; ".join(errors))


class _SafeQuotationLoader(yaml.SafeLoader):
    """SafeLoader không cho alias (chống alias bomb), không cho khoá lặp, và đọc số thập phân thành Decimal."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if isinstance(key, Hashable):
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"khoá {key!r} bị lặp trong cùng một mapping (giá trị sau sẽ ghi đè âm thầm)",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep)

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            raise yaml.constructor.ConstructorError(
                None, None, "alias (*) không được phép trong file báo giá", event.start_mark
            )
        return super().compose_node(parent, index)


def _construct_decimal(loader: yaml.SafeLoader, node: yaml.Node) -> Decimal:
    text = loader.construct_scalar(node).replace("_", "")
    if ":" in text:
        raise yaml.constructor.ConstructorError(None, None, _SEXAGESIMAL_MESSAGE.format(text=text), node.start_mark)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise yaml.constructor.ConstructorError(None, None, f"số không hợp lệ: {text!r}", node.start_mark)
    if not value.is_finite():
        raise yaml.constructor.ConstructorError(None, None, f"số không hữu hạn: {text!r}", node.start_mark)
    return value


def _construct_int(loader: yaml.SafeLoader, node: yaml.Node) -> int:
    text = loader.construct_scalar(node)
    if ":" in text:
        raise yaml.constructor.ConstructorError(None, None, _SEXAGESIMAL_MESSAGE.format(text=text), node.start_mark)
    return yaml.SafeLoader.construct_yaml_int(loader, node)


_SEXAGESIMAL_MESSAGE = (
    "{text!r} bị YAML 1.1 đọc là số hệ 60 (giờ:phút = 1*60+30), không phải chuỗi; "
    "đặt trong dấu nháy nếu là chữ, hoặc viết thành số thường nếu là số"
)
_SafeQuotationLoader.add_constructor("tag:yaml.org,2002:float", _construct_decimal)
_SafeQuotationLoader.add_constructor("tag:yaml.org,2002:int", _construct_int)


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {_normalize(k): _normalize(v) for k, v in value.items()}
    return value


def _format_path(location: tuple) -> str:
    path = ""
    for part in location:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
    return path or "<file>"


def _semantic_errors(file: QuotationFile) -> list[str]:
    errors: list[str] = []

    seen: dict[str, tuple[int, int]] = {}
    items_by_key = {}
    for p_index, package in enumerate(file.quotation.packages):
        for w_index, item in enumerate(package.work_items):
            base = f"quotation.packages[{p_index}].work_items[{w_index}]"
            if item.key in seen:
                errors.append(f"{base}.key: key {item.key!r} bị trùng với hạng mục khác trong file")
            else:
                seen[item.key] = (p_index, w_index)
                items_by_key[item.key] = item
            seen_concepts: set[tuple[str, str]] = set()
            for c_index, concept in enumerate(item.concepts):
                allowed = CONCEPT_VOCABULARY.get(concept.type)
                if allowed is None or concept.name not in allowed:
                    errors.append(
                        f"{base}.concepts[{c_index}]: concept ({concept.type!r}, {concept.name!r}) "
                        f"không nằm trong danh sách cho phép"
                    )
                pair = (concept.type, concept.name)
                if pair in seen_concepts:
                    errors.append(f"{base}.concepts[{c_index}]: concept {pair} bị trùng trong cùng một hạng mục")
                seen_concepts.add(pair)
            if sum(1 for c in item.concepts if c.type == "category") > 1:
                errors.append(f"{base}.concepts: mỗi hạng mục chỉ được có tối đa một concept loại 'category'")

    estimation = file.estimation
    if estimation is not None:
        first_index_by_key: dict[str, int] = {}
        for i, est_item in enumerate(estimation.items):
            if est_item.work_item is not None and est_item.work_item not in items_by_key:
                errors.append(f"estimation.items[{i}].work_item: không có hạng mục nào có key {est_item.work_item!r}")
            elif est_item.work_item is not None:
                if est_item.work_item in first_index_by_key:
                    errors.append(
                        f"estimation.items[{i}].work_item: hạng mục {est_item.work_item!r} bị trùng, đã có mục dự toán "
                        f"estimation.items[{first_index_by_key[est_item.work_item]}]; gộp thành một dòng"
                    )
                else:
                    first_index_by_key[est_item.work_item] = i
        for i, sub in enumerate(estimation.sub_materials):
            for j, usage in enumerate(sub.usages):
                if usage.work_item is not None and usage.work_item not in items_by_key:
                    errors.append(
                        f"estimation.sub_materials[{i}].usages[{j}].work_item: "
                        f"không có hạng mục nào có key {usage.work_item!r}"
                    )
        for i, est_item in enumerate(estimation.items):
            target = items_by_key.get(est_item.work_item)
            if (
                target is not None
                and est_item.material_unit_price is not None
                and est_item.labor_unit_price is not None
                and est_item.profit_margin is not None
            ):
                expected = (est_item.material_unit_price + est_item.labor_unit_price) * (1 + est_item.profit_margin)
                if abs(expected - target.unit_price) > target.unit_price * COST_RELATION_TOLERANCE:
                    errors.append(
                        f"estimation.items[{i}]: profit_margin hoặc đơn giá thành phần không khớp: "
                        f"(material_unit_price + labor_unit_price) * (1 + profit_margin) = {expected} "
                        f"nhưng unit_price của hạng mục {est_item.work_item!r} là {target.unit_price} (lệch quá 0,5%)"
                    )

    computed_total = sum(
        (item.quantity * item.unit_price for package in file.quotation.packages for item in package.work_items),
        Decimal("0"),
    )
    declared = file.quotation.total_amount
    if declared is not None and abs(declared - computed_total) > TOTAL_AMOUNT_TOLERANCE:
        errors.append(
            f"quotation.total_amount: {declared} không bằng tổng quantity * unit_price các hạng mục ({computed_total})"
        )
    return errors


def load_quotation_text(text: str, source_name: str = "") -> QuotationFile:
    if text.startswith("﻿"):
        text = text[1:]
    try:
        raw = yaml.load(text, Loader=_SafeQuotationLoader)
    except yaml.YAMLError as exc:
        raise QuotationFileError([f"<file>: YAML không hợp lệ: {exc}"], source_name) from exc
    except RecursionError as exc:
        raise QuotationFileError(["<file>: YAML lồng quá sâu"], source_name) from exc
    except ValueError as exc:  # ví dụ số nguyên hơn 4300 chữ số
        raise QuotationFileError([f"<file>: giá trị không hợp lệ: {exc}"], source_name) from exc
    if not isinstance(raw, dict):
        raise QuotationFileError(["<file>: nội dung gốc phải là một mapping YAML"], source_name)

    try:
        file = QuotationFile.model_validate(_normalize(raw))
    except ValidationError as exc:
        errors = [f"{_format_path(tuple(e['loc']))}: {e['msg']}" for e in exc.errors()]
        raise QuotationFileError(errors, source_name) from exc

    errors = check_column_limits(file)  # trước các phép tính tổng, để số quá lớn không làm tràn Decimal
    if not errors:
        try:
            errors = _semantic_errors(file)
        except ArithmeticError as exc:
            errors = [f"<file>: số quá lớn để tính tổng: {exc}"]
    if errors:
        raise QuotationFileError(errors, source_name)

    if file.quotation.total_amount is None:
        total = sum(
            (item.quantity * item.unit_price for package in file.quotation.packages for item in package.work_items),
            Decimal("0"),
        )
        file.quotation.total_amount = total
    return file


def load_quotation_file(path: Path) -> QuotationFile:
    path = Path(path)
    return load_quotation_text(path.read_text(encoding="utf-8"), path.name)
