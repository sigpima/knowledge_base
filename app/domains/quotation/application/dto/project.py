from dataclasses import dataclass, field

from .quotation import QuotationData, CreateQuotationData


@dataclass
class CreateProjectData:
    name: str
    address: str
    source_file: str | None = None
    estimated_workdays: list[int] | None = None
    quotations: list[CreateQuotationData] = field(default_factory=list)


@dataclass
class ProjectData:
    project_id: int
    name: str
    address: str
    source_file: str | None = None
    estimated_workdays: list[int] | None = None
    quotations: list[QuotationData] = field(default_factory=list)
