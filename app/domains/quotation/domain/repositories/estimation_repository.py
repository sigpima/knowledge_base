from abc import ABC, abstractmethod

from ...application.dto import EstimationData, EstimationWorkItemData, CreateEstimationBundleData


class EstimationRepository(ABC):

    @abstractmethod
    def get_by_project_id(self, project_id: int) -> EstimationData | None:
        pass

    @abstractmethod
    def get_work_item_detail(self, item_id: int) -> EstimationWorkItemData | None:
        pass

    @abstractmethod
    def create(self, project_id: int, data: CreateEstimationBundleData) -> None:
        pass
