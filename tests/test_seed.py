from pathlib import Path

from sqlalchemy import func, select

from app.domains.quotation.infrastructure.persistence.models import ProjectModel, WorkItemModel
from app.infrastructure.database.postgres.session import SessionLocal
from scripts.seed import seed

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_seed_loads_all_files_and_is_idempotent(db_session):
    files = sorted(SAMPLE_DIR.glob("*.yaml"))

    first = seed(SessionLocal, SAMPLE_DIR)
    projects_after_first = _count(db_session, ProjectModel)
    work_items_after_first = _count(db_session, WorkItemModel)
    db_session.rollback()  # nhả khoá đọc, nếu không TRUNCATE của lần seed sau sẽ chờ mãi
    second = seed(SessionLocal, SAMPLE_DIR)

    assert len(first) == len(second) == len(files) >= 20
    assert projects_after_first == len(files)
    assert _count(db_session, ProjectModel) == projects_after_first
    assert _count(db_session, WorkItemModel) == work_items_after_first


def test_seed_replaces_unrelated_existing_data(db_session):
    db_session.add(ProjectModel(name="Công trình cũ không thuộc bộ mẫu", address="x"))
    db_session.commit()

    seed(SessionLocal, SAMPLE_DIR)

    names = db_session.execute(select(ProjectModel.name)).scalars().all()
    assert "Công trình cũ không thuộc bộ mẫu" not in names
