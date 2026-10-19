from abc import ABC, abstractmethod

from ...application.dto import CreateExtraQuotationData, ExtraQuotationData


class ExtraQuotationRepository(ABC):

    @abstractmethod
    def get_by_id(self, extra_quotation_id: int) -> ExtraQuotationData | None:
        pass

    @abstractmethod
    def save(self, project_id: int, data: CreateExtraQuotationData) -> ExtraQuotationData:
        pass
