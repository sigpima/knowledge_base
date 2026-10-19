def test_domain_repository_ports_import_successfully():
    from app.domains.quotation.domain.repositories import (
        QuotationRepository,
        WorkItemRepository,
    )
    assert QuotationRepository is not None
    assert WorkItemRepository is not None


def test_quotation_version_repository_no_longer_exists():
    import app.domains.quotation.domain.repositories as repositories_pkg
    assert not hasattr(repositories_pkg, "QuotationVersionRepository")
