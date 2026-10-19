"""Ánh xạ `QuotationFile` (đã kiểm tra) sang các DTO `Create*Data` hiện có."""
from dataclasses import dataclass, field

from app.domains.quotation.application.dto import (
    CreateConceptData,
    CreateEstimationBundleData,
    CreateEstimationData,
    CreateEstimationWorkItemData,
    CreateExtraQuotationData,
    CreateItemSubData,
    CreateLaborInfoData,
    CreateLaborInfoProcessData,
    CreateMainMaterialData,
    CreatePaymentTermData,
    CreateProductToBuyData,
    CreateProjectData,
    CreateQuotationData,
    CreateQuotationPackageData,
    CreateScopeTermData,
    CreateSubMaterialData,
    CreateTotalDetailData,
    CreateWarrantyTermData,
    CreateWorkItemData,
    CreateWorkStepData,
    QuotationKnowledge,
)

from .schema import QuotationFile


@dataclass(frozen=True)
class WorkItemSlot:
    """Vị trí hạng mục trong báo giá (chỉ số gói, chỉ số hạng mục trong gói)."""

    package_index: int
    item_index: int


@dataclass
class TermsData:
    scope: list[CreateScopeTermData] = field(default_factory=list)
    payment: list[CreatePaymentTermData] = field(default_factory=list)
    warranty: CreateWarrantyTermData | None = None


def to_knowledge(file: QuotationFile, source_file: str) -> tuple[QuotationKnowledge, dict[str, WorkItemSlot]]:
    currency = file.quotation.currency
    slots: dict[str, WorkItemSlot] = {}
    packages: list[CreateQuotationPackageData] = []
    for p_index, package in enumerate(file.quotation.packages):
        work_items: list[CreateWorkItemData] = []
        for w_index, item in enumerate(package.work_items):
            slots[item.key] = WorkItemSlot(p_index, w_index)
            work_items.append(
                CreateWorkItemData(
                    name=item.name,
                    description=item.description,
                    unit=item.unit,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    currency=currency,
                    work_steps=[
                        CreateWorkStepData(
                            sequence=s_index,
                            name=step.name,
                            product_name=step.product_name,
                            layers=step.layers,
                            note=step.note,
                        )
                        for s_index, step in enumerate(item.steps, start=1)
                    ],
                    concepts=[CreateConceptData(type=c.type, name=c.name) for c in item.concepts],
                )
            )
        packages.append(CreateQuotationPackageData(name=package.name, sequence=p_index + 1, work_items=work_items))

    quotation = CreateQuotationData(
        quotation_code=file.quotation.code,
        project_name=file.project.name,
        project_address=file.project.address,
        issue_date=file.quotation.issue_date,
        total_amount=file.quotation.total_amount,
        currency=currency,
        packages=packages,
    )
    project = CreateProjectData(
        name=file.project.name,
        address=file.project.address,
        source_file=source_file,
        estimated_workdays=file.project.estimated_workdays,
    )
    return QuotationKnowledge(quotation=quotation, project=project), slots


def to_estimation_bundle(file: QuotationFile, item_ids_by_key: dict[str, int]) -> CreateEstimationBundleData | None:
    spec = file.estimation
    if spec is None:
        return None

    items: list[CreateEstimationWorkItemData] = []
    for est in spec.items:
        labor = None
        if est.labor is not None:
            labor = CreateLaborInfoData(
                **{k: v for k, v in est.labor.model_dump().items() if k != "processes"},
                processes=[CreateLaborInfoProcessData(**p.model_dump()) for p in est.labor.processes],
            )
        items.append(
            CreateEstimationWorkItemData(
                item_id=item_ids_by_key[est.work_item] if est.work_item is not None else None,
                labor_info=labor,
                main_materials=[CreateMainMaterialData(**m.model_dump()) for m in est.main_materials],
                **{
                    k: v
                    for k, v in est.model_dump().items()
                    if k not in ("work_item", "labor", "main_materials")
                },
            )
        )

    sub_materials = [
        CreateSubMaterialData(
            type=sub.type,
            name=sub.name,
            unit=sub.unit,
            unit_price=sub.unit_price,
            total_price=sub.total_price,
            usages=[
                CreateItemSubData(
                    item_id=item_ids_by_key[usage.work_item] if usage.work_item is not None else None,
                    amount=usage.amount,
                    total_price=usage.total_price,
                )
                for usage in sub.usages
            ],
        )
        for sub in spec.sub_materials
    ]
    return CreateEstimationBundleData(
        estimation=CreateEstimationData(
            total_price=spec.total_price,
            total_details=[CreateTotalDetailData(type=t.type, name=t.name, price=t.price) for t in spec.total_details],
            estimation_work_items=items,
        ),
        sub_materials=sub_materials,
        products_to_buy=[CreateProductToBuyData(**p.model_dump()) for p in spec.products_to_buy],
    )


def to_extra_quotations(file: QuotationFile) -> list[CreateExtraQuotationData]:
    return [CreateExtraQuotationData(**extra.model_dump()) for extra in file.extras]


def to_terms(file: QuotationFile) -> TermsData:
    quotation = file.quotation
    return TermsData(
        scope=[CreateScopeTermData(**t.model_dump()) for t in quotation.scope_terms],
        payment=[
            CreatePaymentTermData(sequence=index, **t.model_dump())
            for index, t in enumerate(quotation.payment_terms, start=1)
        ],
        warranty=CreateWarrantyTermData(**quotation.warranty.model_dump()) if quotation.warranty else None,
    )
