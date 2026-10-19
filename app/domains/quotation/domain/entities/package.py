from typing import List

from .work_item import WorkItem


class QuotationPackage():

    def __init__(
        self,
        package_id: int,
        quotation_id: int,
        work_items: List["WorkItem"],
        sequence: int,
        name: str,
        total_amount: int
    ):
        self.package_id = package_id
        self.quotation_id = quotation_id
        self.work_items = work_items
        self.sequence = sequence
        self.name = name
        self.total_amount = total_amount
