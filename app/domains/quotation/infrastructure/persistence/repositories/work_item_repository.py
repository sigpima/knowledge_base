from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ....domain.entities import WorkItem
from ....domain.repositories.work_item_repository import WorkItemRepository
from ....domain.value_objects.money import Money
from ....domain.value_objects.quantity import Quantity
from ..models import ConceptModel, WorkItemModel


class SqlAlchemyWorkItemRepository(WorkItemRepository):

    def __init__(self, session: Session):
        self.session = session

    # -- WorkItemRepository port (single-item CRUD) -------------------------

    def get_by_id(self, item_id: int) -> WorkItem | None:
        model = self.session.get(WorkItemModel, item_id)
        if model is None:
            return None
        return self._to_entity(model)

    def save(self, work_item: WorkItem) -> WorkItem:
        if work_item.item_id is None:
            model = WorkItemModel(
                package_id=work_item.package_id,
                sequence=work_item.sequence,
                name=work_item.name,
                description=work_item.description,
                quantity=work_item.quantity.value,
                unit=work_item.quantity.unit,
                unit_price=work_item.unit_price.amount,
                total_price=work_item.total_price.amount,
                currency=work_item.unit_price.currency,
            )
            self.session.add(model)
        else:
            model = self.session.get(WorkItemModel, work_item.item_id)
            model.package_id = work_item.package_id
            model.sequence = work_item.sequence
            model.name = work_item.name
            model.description = work_item.description
            model.quantity = work_item.quantity.value
            model.unit = work_item.quantity.unit
            model.unit_price = work_item.unit_price.amount
            model.total_price = work_item.total_price.amount
            model.currency = work_item.unit_price.currency

        self.session.flush()
        self.session.commit()
        return self._to_entity(model)

    def delete(self, item_id: int) -> None:
        model = self.session.get(WorkItemModel, item_id)
        if model is not None:
            self.session.delete(model)
            self.session.commit()

    def _to_entity(self, model: WorkItemModel) -> WorkItem:
        # work_steps/concepts intentionally left empty -- mapping the nested
        # product/concept graph is out of scope here; see this plan's header.
        return WorkItem(
            item_id=model.item_id,
            package_id=model.package_id,
            sequence=model.sequence,
            name=model.name,
            description=model.description or "",
            quantity=Quantity(
                value=model.quantity if model.quantity is not None else Decimal("0"),
                unit=model.unit or "unknown",
            ),
            unit_price=Money(
                amount=model.unit_price if model.unit_price is not None else Decimal("0"),
                currency=model.currency,
            ),
        )

    # -- Search / filter queries ---------------------------------------------

    def _filtered_query(self, text: str | None, concept_filters: dict[str, str] | None):
        query = self.session.query(WorkItemModel)

        if text:
            pattern = f"%{text}%"
            query = query.filter(
                WorkItemModel.name.ilike(pattern) | WorkItemModel.description.ilike(pattern)
            )

        for concept_type, concept_name in (concept_filters or {}).items():
            query = query.filter(
                WorkItemModel.concepts.any(
                    and_(ConceptModel.type == concept_type, ConceptModel.name == concept_name)
                )
            )

        return query

    def search(
        self,
        text: str | None = None,
        concept_filters: dict[str, str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        items = self._filtered_query(text, concept_filters).limit(limit).all()

        return [
            {
                "item_id": item.item_id,
                "name": item.name,
                "description": item.description,
                "unit": item.unit,
                "unit_price": item.unit_price,
            }
            for item in items
        ]

    def count(
        self,
        text: str | None = None,
        concept_filters: dict[str, str] | None = None,
    ) -> int:
        return self._filtered_query(text, concept_filters).count()
