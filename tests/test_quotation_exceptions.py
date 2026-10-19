from app.domains.quotation.exception import EntityNotFoundError, QuotationDomainError


def test_entity_not_found_is_a_quotation_domain_error():
    error = EntityNotFoundError(entity_name="WorkItem", entity_id=42)
    assert isinstance(error, QuotationDomainError)
    assert error.entity_name == "WorkItem"
    assert error.entity_id == 42
    assert "WorkItem" in str(error)
    assert "42" in str(error)
