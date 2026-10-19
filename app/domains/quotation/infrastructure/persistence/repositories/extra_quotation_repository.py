from sqlalchemy.orm import Session

from app.infrastructure.observability.logger import get_logger
from ....domain.repositories.extra_quotation_repository import ExtraQuotationRepository
from ....application.dto import CreateExtraQuotationData, ExtraQuotationData
from ..models import ExtraQuotationModel

logger = get_logger(__name__)


class SqlAlchemyExtraQuotationRepository(ExtraQuotationRepository):

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, extra_quotation_id: int) -> ExtraQuotationData | None:
        model = self.session.get(ExtraQuotationModel, extra_quotation_id)
        if model is None:
            return None
        return self._to_data(model)

    def save(self, project_id: int, data: CreateExtraQuotationData) -> ExtraQuotationData:
        try:
            model = ExtraQuotationModel(
                project_id=project_id,
                issue_date=data.issue_date,
                total_amount=data.total_amount,
                currency=data.currency,
                description=data.description,
                quantity=data.quantity,
                unit=data.unit,
                unit_price=data.unit_price,
                extra_metadata=data.metadata,
            )
            self.session.add(model)
            self.session.flush()
            return self._to_data(model)
        except Exception:
            logger.error("Failed to save extra quotation for project %r", project_id, exc_info=True)
            self.session.rollback()
            raise

    def _to_data(self, model: ExtraQuotationModel) -> ExtraQuotationData:
        return ExtraQuotationData(
            extra_quotation_id=model.extra_quotation_id,
            issue_date=model.issue_date,
            total_amount=model.total_amount,
            currency=model.currency,
            description=model.description,
            quantity=model.quantity,
            unit=model.unit,
            unit_price=model.unit_price,
            metadata=model.extra_metadata,
        )
