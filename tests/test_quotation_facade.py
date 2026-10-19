from decimal import Decimal

from app.domains.quotation.domain.entities import WorkItem
from app.domains.quotation.domain.repositories import WorkItemRepository
from app.domains.quotation.application.dto import CreateWorkItemData
from app.domains.quotation.application.services.work_item_service import WorkItemApplicationService
from app.domains.quotation.facade import QuotationFacade


class FakeWorkItemRepository(WorkItemRepository):
    def __init__(self):
        self._items: dict[int, WorkItem] = {}
        self._next_id = 1

    def get_by_id(self, item_id: int) -> WorkItem | None:
        return self._items.get(item_id)

    def save(self, work_item: WorkItem) -> WorkItem:
        if work_item.item_id is None:
            work_item.item_id = self._next_id
            self._next_id += 1
        self._items[work_item.item_id] = work_item
        return work_item

    def delete(self, item_id: int) -> None:
        self._items.pop(item_id, None)


def test_facade_creates_and_retrieves_a_work_item():
    facade = QuotationFacade(WorkItemApplicationService(FakeWorkItemRepository()))

    created = facade.create_work_item(
        package_id=1,
        sequence=1,
        data=CreateWorkItemData(
            name="Sơn lót tường",
            description="Thi công sơn lót",
            unit="m2",
            unit_price=Decimal("50000"),
            quantity=Decimal("10"),
            currency="VND",
        ),
    )

    assert created.item_id == 1
    fetched = facade.get_work_item(created.item_id)
    assert fetched.name == "Sơn lót tường"


def test_facade_returns_none_for_missing_work_item():
    facade = QuotationFacade(WorkItemApplicationService(FakeWorkItemRepository()))
    assert facade.get_work_item(999) is None
