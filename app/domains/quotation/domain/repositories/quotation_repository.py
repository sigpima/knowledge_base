from abc import ABC, abstractmethod

from ..entities import Quotation


class QuotationRepository(ABC):

    @abstractmethod
    def get_by_id(self, quotation_id: int) -> Quotation:
        pass

    @abstractmethod
    def save(self, quotation: Quotation) -> None:
        pass