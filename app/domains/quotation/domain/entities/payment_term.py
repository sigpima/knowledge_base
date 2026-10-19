from decimal import Decimal


class QuotationPaymentTerm():

    def __init__(
        self,
        payment_term_id: int,
        quotation_id: int,
        sequence: int,
        percentage: Decimal,
        trigger_type: str,
        trigger_description: str
    ):
        self.payment_term_id = payment_term_id
        self.quotation_id = quotation_id
        self.sequence = sequence
        self.percentage = percentage
        self.trigger_type = trigger_type
        self.trigger_description = trigger_description
