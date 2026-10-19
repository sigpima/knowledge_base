from dataclasses import dataclass


@dataclass
class CreateConceptData:
    type: str
    name: str


@dataclass
class ConceptData:
    concept_id: int
    type: str
    name: str
