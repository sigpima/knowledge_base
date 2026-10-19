"""Xoá sạch dữ liệu schema `quotation` rồi nạp lại toàn bộ file YAML mẫu.

    python -m scripts.seed data/sample

Chạy lại bao nhiêu lần cũng cho cùng kết quả (không nhân đôi dữ liệu).
"""
import argparse
from pathlib import Path
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.quotation.application.services.ingest.loader import load_quotation_file
from app.domains.quotation.application.services.ingest.writer import IngestResult, ingest_quotation
from app.infrastructure.database import Base
from app.infrastructure.database.postgres.session import SessionLocal, init_db


def _reset(session: Session) -> None:
    tables = ", ".join(table.fullname for table in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session.commit()


def seed(session_factory: Callable[[], Session], directory: Path) -> list[IngestResult]:
    with session_factory() as session:
        _reset(session)
    results: list[IngestResult] = []
    for path in sorted(Path(directory).glob("*.yaml")):
        file = load_quotation_file(path)
        with session_factory() as session:
            results.append(ingest_quotation(session, file, path.name))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("data/sample"))
    args = parser.parse_args()
    init_db()
    results = seed(SessionLocal, args.directory)
    work_items = sum(r.work_item_count for r in results)
    print(f"Đã nạp {len(results)} công trình ({work_items} hạng mục) từ {args.directory}")


if __name__ == "__main__":
    main()
