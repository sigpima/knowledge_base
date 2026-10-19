from dataclasses import dataclass

from app.core.domain import Knowledge
from .quotation import CreateQuotationData
from .project import CreateProjectData


@dataclass
class QuotationKnowledge(Knowledge):
    quotation: CreateQuotationData
    project: CreateProjectData
    document_id: str | None = None
