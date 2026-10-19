from abc import ABC, abstractmethod

from ..entities import WorkItem


class WorkItemRepository(ABC):

    @abstractmethod
    def get_by_id(self, item_id: int) -> WorkItem | None:
        pass

    @abstractmethod
    def save(self, work_item: WorkItem) -> WorkItem:
        pass

    @abstractmethod
    def delete(self, item_id: int) -> None:
        pass