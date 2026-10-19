from decimal import Decimal

from app.domains.quotation.domain.entities import WorkItem
from app.domains.quotation.domain.repositories import WorkItemRepository
from app.domains.quotation.application.dto import CreateWorkItemData
from app.domains.quotation.application.services.work_item_service import WorkItemApplicationService


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


def test_create_persists_and_returns_a_work_item_with_computed_total():
    service = WorkItemApplicationService(FakeWorkItemRepository())

    result = service.create(
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

    assert result.item_id == 1
    assert result.total_price == Decimal("500000")


def test_get_returns_none_for_missing_item():
    service = WorkItemApplicationService(FakeWorkItemRepository())
    assert service.get(999) is None
