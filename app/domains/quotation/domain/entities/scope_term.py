class QuotationScopeTerm():

    def __init__(
        self,
        scope_term_id: int,
        quotation_id: int,
        scope_type: str,
        term_type: str,
        description: str,
        amount: str
    ):
        self.scope_term_id = scope_term_id
        self.quotation_id = quotation_id
        self.scope_type = scope_type
        self.term_type = term_type
        self.description = description
        self.amount = amount
