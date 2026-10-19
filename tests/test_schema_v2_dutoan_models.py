from sqlalchemy import inspect

DU_TOAN_TABLES = {
    "estimation", "total_detail", "estimation_work_item", "labor_info",
    "labor_info_process", "main_material", "product_to_buy", "sub_material",
    "item_sub",
}


def test_all_dutoan_tables_exist(db_engine):
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names(schema="quotation"))
    assert DU_TOAN_TABLES <= tables


def test_estimation_work_item_links_to_work_item_nullable(db_engine):
    inspector = inspect(db_engine)
    fks = inspector.get_foreign_keys("estimation_work_item", schema="quotation")
    targets = {(fk["referred_table"], tuple(fk["referred_columns"])) for fk in fks}
    assert ("work_item", ("item_id",)) in targets
    columns = {c["name"]: c for c in inspector.get_columns("estimation_work_item", schema="quotation")}
    assert columns["item_id"]["nullable"] is True


def test_item_sub_uses_surrogate_pk_with_nullable_item_id(db_engine):
    inspector = inspect(db_engine)
    pk = inspector.get_pk_constraint("item_sub", schema="quotation")
    assert pk["constrained_columns"] == ["item_sub_id"]
    columns = {c["name"]: c for c in inspector.get_columns("item_sub", schema="quotation")}
    assert columns["item_id"]["nullable"] is True
