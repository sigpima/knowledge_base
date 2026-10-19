from decimal import Decimal


class QuotationWarrantyTerm():

    def __init__(
        self,
        warranty_term_id: int,
        quotation_id: int,
        period: int,
        period_unit: str,
        extend_percent: Decimal,
        extend_period: int
    ):
        self.warranty_term_id = warranty_term_id
        self.quotation_id = quotation_id
        self.period = period
        self.period_unit = period_unit
        self.extend_percent = extend_percent
        self.extend_period = extend_period
