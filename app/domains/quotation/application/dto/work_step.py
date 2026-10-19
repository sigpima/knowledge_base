from dataclasses import dataclass


@dataclass
class CreateWorkStepData:
    sequence: int
    name: str
    description: str | None = None
    product_name: str | None = None
    layers: int | None = None
    note: str | None = None


@dataclass
class WorkStepData:
    step_id: int
    sequence: int
    name: str
    description: str | None = None
    product_name: str | None = None
    layers: int | None = None
    note: str | None = None
