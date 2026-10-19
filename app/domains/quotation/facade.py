from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from .application.dto import CreateWorkItemData, EstimationData, EstimationWorkItemData, WorkItemData
from .application.services.estimation_service import EstimationApplicationService, EstimationDetailDiff
from .application.services.project_service import (
    CostBreakdownComparison,
    ProjectApplicationService,
    ProjectLaborCostComparison,
)
from .application.services.work_item_service import PriceAnalysis, WorkItemApplicationService
from .infrastructure.persistence.repositories.estimation_repository import SqlAlchemyEstimationRepository
from .infrastructure.persistence.repositories.quotation_repository import SqlAlchemyQuotationRepository
from .infrastructure.persistence.repositories.work_item_repository import SqlAlchemyWorkItemRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .application.dto.quotation_knowledge import QuotationKnowledge
    from .infrastructure.persistence.models import QuotationModel


class QuotationFacade:
    """Single entry point `app/core/` is allowed to know about for the
    `quotation` domain -- callers outside this package construct it via
    `from_session()` and never import anything under
    `infrastructure/persistence/repositories/` directly, keeping that
    package's adapters an implementation detail of the domain."""

    def __init__(
        self,
        work_item_service: WorkItemApplicationService,
        *,
        project_service: Optional[ProjectApplicationService] = None,
        estimation_service: Optional[EstimationApplicationService] = None,
        work_item_repository: Optional[SqlAlchemyWorkItemRepository] = None,
        quotation_repository: Optional[SqlAlchemyQuotationRepository] = None,
    ):
        self.work_item_service = work_item_service
        self._project_service = project_service
        self._estimation_service = estimation_service
        self._work_item_repository = work_item_repository
        self._quotation_repository = quotation_repository

    @classmethod
    def from_session(cls, session: "Session") -> "QuotationFacade":
        """Production factory: wires every adapter to the same SQLAlchemy
        session, mirroring the "caller owns the session" convention
        (`app/core/services/knowledge_service.py` opens `with SessionLocal()
        as session:` and constructs one facade per call)."""
        work_item_repository = SqlAlchemyWorkItemRepository(session)
        return cls(
            WorkItemApplicationService(work_item_repository, session),
            project_service=ProjectApplicationService(session),
            estimation_service=EstimationApplicationService(SqlAlchemyEstimationRepository(session), session),
            work_item_repository=work_item_repository,
            quotation_repository=SqlAlchemyQuotationRepository(session),
        )

    # -- Work item CRUD --------------------------------------------------

    def create_work_item(self, package_id: int, sequence: int, data: CreateWorkItemData) -> WorkItemData:
        return self.work_item_service.create(package_id, sequence, data)

    def get_work_item(self, work_item_id: int) -> WorkItemData | None:
        return self.work_item_service.get(work_item_id)

    # -- Ingestion persistence --------------------------------------------

    def persist_knowledge(self, knowledge: "QuotationKnowledge") -> "QuotationModel":
        return self._quotation_repository.persist(knowledge)

    # -- Price analysis ----------------------------------------------------

    def compare_work_item_price(self, work_item_data) -> PriceAnalysis:
        return self.work_item_service.compare_price(work_item_data)

    def compare_work_item_price_by_item_id(self, item_id: int) -> PriceAnalysis | None:
        return self.work_item_service.compare_price_by_item_id(item_id)

    # -- Search / summary ---------------------------------------------------

    def search_work_items(
        self, text: str | None = None, concept_filters: Dict[str, str] | None = None, limit: int = 50
    ) -> list:
        return self._work_item_repository.search(text=text, concept_filters=concept_filters, limit=limit)

    def count_work_items(self, text: str | None = None, concept_filters: Dict[str, str] | None = None) -> int:
        return self._work_item_repository.count(text=text, concept_filters=concept_filters)

    def summarize_quotation(self, quotation_id: int) -> Dict[str, Any] | None:
        return self._quotation_repository.summarize_quotation(quotation_id)

    def get_quotation(self, quotation_id: int) -> Dict[str, Any] | None:
        return self._quotation_repository.get_quotation_detail(quotation_id)

    def find_quotations(
        self, project_id: Optional[int], order_by: str, limit: int
    ) -> tuple[list, int] | None:
        return self._quotation_repository.find_quotations(project_id, order_by, limit)

    def summarize_project(self, project_id: int) -> Dict[str, Any] | None:
        return self._quotation_repository.summarize_project(project_id)

    # -- Cross-project / cross-hạng-mục comparisons -------------------------

    def compare_project_labor_cost(self, project_id: int) -> ProjectLaborCostComparison | None:
        return self._project_service.compare_labor_cost(project_id)

    def compare_work_item_detail(self, item_id_a: int, item_id_b: int) -> EstimationDetailDiff | None:
        return self._estimation_service.compare_detail(item_id_a, item_id_b)

    def compare_project_cost_breakdown(self, project_id: int, cost_type: str) -> CostBreakdownComparison | None:
        return self._project_service.compare_cost_breakdown(project_id, cost_type)

    # -- Dự toán lookup -------------------------------------------------------

    def get_estimation(self, project_id: int) -> EstimationData | None:
        return self._estimation_service.get_estimation(project_id)

    def get_estimation_work_item(self, item_id: int) -> EstimationWorkItemData | None:
        return self._estimation_service.get_estimation_work_item(item_id)
