from typing import List

from .quotation import Quotation


class Project():

    def __init__(
        self,
        project_id: int,
        name: str,
        address: str,
        quotations: List["Quotation"]
    ):
        self.project_id = project_id
        self.name = name
        self.address = address
        self.quotations = quotations
