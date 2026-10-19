import unicodedata
from typing import Callable, List, Dict, Any

from sqlalchemy.orm import Session

from app.domains.quotation.application.dto import WorkItemData, EstimationData, EstimationWorkItemData
from app.domains.quotation.facade import QuotationFacade
from app.infrastructure.database.postgres.session import SessionLocal
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)


class KnowledgeService:
    """Các truy vấn đọc dữ liệu báo giá/dự toán; mỗi method mở một session riêng."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        # Injectable so the MCP server can pass ReadonlySessionLocal: a
        # session with `default_transaction_read_only=on`, so any write
        # attempt through this instance fails at the Postgres level.
        self.session_factory = session_factory

    def get_work_item(self, item_id: int) -> WorkItemData | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.get_work_item(item_id)

    def search_work_items(
        self,
        text: str | None = None,
        concept_filters: Dict[str, str] | None = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        # Dữ liệu lưu ở dạng NFC; câu truy vấn gõ trên bàn phím/hệ điều hành khác có thể là NFD.
        text = unicodedata.normalize("NFC", text) if text is not None else None
        if concept_filters:
            concept_filters = {
                unicodedata.normalize("NFC", key): unicodedata.normalize("NFC", value)
                for key, value in concept_filters.items()
            }
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            items = facade.search_work_items(text=text, concept_filters=concept_filters, limit=limit)
            matched_count = facade.count_work_items(text=text, concept_filters=concept_filters)
            return {"items": items, "matched_count": matched_count}

    def summarize_quotation(self, quotation_id: int) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.summarize_quotation(quotation_id)

    def get_quotation(self, quotation_id: int) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.get_quotation(quotation_id)

    def find_quotations(
        self, project_id: int | None, order_by: str, limit: int
    ) -> tuple[List[Dict[str, Any]], int] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.find_quotations(project_id, order_by, limit)

    def summarize_project(self, project_id: int) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.summarize_project(project_id)

    def compare_work_item_price(self, item_id: int) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            analysis = facade.compare_work_item_price_by_item_id(item_id)
            if analysis is None:
                return None
            return {
                "matched_count": analysis.matched_count,
                "historical_min": analysis.historical_min,
                "historical_max": analysis.historical_max,
                "historical_avg": analysis.historical_avg,
                "pct_diff_from_avg": analysis.pct_diff_from_avg,
                "matched_items": [
                    {
                        "item_id": m.item_id,
                        "name": m.name,
                        "project_name": m.project_name,
                        "unit_price": m.unit_price,
                        "name_similarity_score": m.name_similarity_score,
                    }
                    for m in analysis.matched_items
                ],
            }

    def compare_project_labor_cost(self, project_id: int) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            comparison = facade.compare_project_labor_cost(project_id)
            if comparison is None:
                return None
            return {
                "project_id": comparison.project_id,
                "project_name": comparison.project_name,
                "total_out_cost": comparison.total_out_cost,
                "total_area": comparison.total_area,
                "matched_count": comparison.matched_count,
                "matched_projects": [
                    {
                        "project_id": m.project_id,
                        "name": m.name,
                        "total_out_cost": m.total_out_cost,
                        "total_area": m.total_area,
                        "cost_diff": m.cost_diff,
                        "cost_diff_pct": m.cost_diff_pct,
                        "similarity_score": m.similarity_score,
                    }
                    for m in comparison.matched_projects
                ],
            }

    def compare_work_item_detail(self, item_id_a: int, item_id_b: int) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            diff = facade.compare_work_item_detail(item_id_a, item_id_b)
            if diff is None:
                return None
            return {
                "item_id_a": diff.item_id_a,
                "item_id_b": diff.item_id_b,
                "name_a": diff.name_a,
                "name_b": diff.name_b,
                "unit_price_a": diff.unit_price_a,
                "unit_price_b": diff.unit_price_b,
                "price_diff": diff.price_diff,
                "price_diff_pct": diff.price_diff_pct,
                "material_unit_price_a": diff.material_unit_price_a,
                "material_unit_price_b": diff.material_unit_price_b,
                "material_unit_price_diff": diff.material_unit_price_diff,
                "labor_unit_price_a": diff.labor_unit_price_a,
                "labor_unit_price_b": diff.labor_unit_price_b,
                "labor_unit_price_diff": diff.labor_unit_price_diff,
                "profit_margin_a": diff.profit_margin_a,
                "profit_margin_b": diff.profit_margin_b,
                "profit_margin_diff": diff.profit_margin_diff,
                "labor_info_diff": None if diff.labor_info_diff is None else {
                    "final_unit_price_type_a": diff.labor_info_diff.final_unit_price_type_a,
                    "final_unit_price_type_b": diff.labor_info_diff.final_unit_price_type_b,
                    "labor_coeff_a": diff.labor_info_diff.labor_coeff_a,
                    "labor_coeff_b": diff.labor_info_diff.labor_coeff_b,
                    "labor_coeff_diff": diff.labor_info_diff.labor_coeff_diff,
                    "kn_manday_a": diff.labor_info_diff.kn_manday_a,
                    "kn_manday_b": diff.labor_info_diff.kn_manday_b,
                    "kn_manday_diff": diff.labor_info_diff.kn_manday_diff,
                    "main_out_manday_a": diff.labor_info_diff.main_out_manday_a,
                    "main_out_manday_b": diff.labor_info_diff.main_out_manday_b,
                    "main_out_manday_diff": diff.labor_info_diff.main_out_manday_diff,
                    "sub_out_manday_a": diff.labor_info_diff.sub_out_manday_a,
                    "sub_out_manday_b": diff.labor_info_diff.sub_out_manday_b,
                    "sub_out_manday_diff": diff.labor_info_diff.sub_out_manday_diff,
                    "area_a": diff.labor_info_diff.area_a,
                    "area_b": diff.labor_info_diff.area_b,
                    "area_diff": diff.labor_info_diff.area_diff,
                },
                "materials": [
                    {
                        "match_type": m.match_type,
                        "name_similarity_score": m.name_similarity_score,
                        "a": None if m.a is None else {
                            "product_name": m.a.product_name,
                            "layers": m.a.layers,
                            "construction_loss": m.a.construction_loss,
                            "theoretical_rate": m.a.theoretical_rate,
                            "unit_price_per_m2": m.a.unit_price_per_m2,
                            "total_price_area_based": m.a.total_price_area_based,
                        },
                        "b": None if m.b is None else {
                            "product_name": m.b.product_name,
                            "layers": m.b.layers,
                            "construction_loss": m.b.construction_loss,
                            "theoretical_rate": m.b.theoretical_rate,
                            "unit_price_per_m2": m.b.unit_price_per_m2,
                            "total_price_area_based": m.b.total_price_area_based,
                        },
                    }
                    for m in diff.materials
                ],
                "processes": [
                    {
                        "match_type": p.match_type,
                        "name_similarity_score": p.name_similarity_score,
                        "a": None if p.a is None else {
                            "name": p.a.name,
                            "main_labors_kn": p.a.main_labors_kn,
                            "main_labors_out": p.a.main_labors_out,
                            "sub_labors_out": p.a.sub_labors_out,
                            "days": p.a.days,
                            "kn_manday": p.a.kn_manday,
                            "main_out_manday": p.a.main_out_manday,
                            "sub_out_manday": p.a.sub_out_manday,
                        },
                        "b": None if p.b is None else {
                            "name": p.b.name,
                            "main_labors_kn": p.b.main_labors_kn,
                            "main_labors_out": p.b.main_labors_out,
                            "sub_labors_out": p.b.sub_labors_out,
                            "days": p.b.days,
                            "kn_manday": p.b.kn_manday,
                            "main_out_manday": p.b.main_out_manday,
                            "sub_out_manday": p.b.sub_out_manday,
                        },
                    }
                    for p in diff.processes
                ],
            }

    def get_estimation(self, project_id: int) -> EstimationData | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.get_estimation(project_id)

    def get_estimation_work_item(self, item_id: int) -> EstimationWorkItemData | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            return facade.get_estimation_work_item(item_id)

    def compare_project_cost_breakdown(self, project_id: int, cost_type: str) -> Dict[str, Any] | None:
        with self.session_factory() as session:
            facade = QuotationFacade.from_session(session)
            comparison = facade.compare_project_cost_breakdown(project_id, cost_type)
            if comparison is None:
                return None
            return {
                "project_id": comparison.project_id,
                "project_name": comparison.project_name,
                "cost_type": comparison.cost_type,
                "price": comparison.price,
                "quotation_total_amount": comparison.quotation_total_amount,
                "pct_of_total": comparison.pct_of_total,
                "matched_count": comparison.matched_count,
                "avg_pct_of_total": comparison.avg_pct_of_total,
                "min_pct_of_total": comparison.min_pct_of_total,
                "max_pct_of_total": comparison.max_pct_of_total,
                "pct_point_diff_from_avg": comparison.pct_point_diff_from_avg,
                "matched_projects": [
                    {
                        "project_id": m.project_id,
                        "name": m.name,
                        "price": m.price,
                        "pct_of_total": m.pct_of_total,
                    }
                    for m in comparison.matched_projects
                ],
            }
