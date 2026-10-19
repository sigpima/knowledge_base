"""Dòng lệnh: `python -m app.cli ingest PATH [PATH...]` (PATH là file hoặc thư mục chứa *.yaml)."""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

from app.domains.quotation.application.services.ingest.loader import QuotationFileError, load_quotation_file
from app.domains.quotation.application.services.ingest.writer import DuplicateProjectError, ingest_quotation
from app.infrastructure.database.postgres.session import SessionLocal, init_db


def _collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted([*path.glob("*.yaml"), *path.glob("*.yml")]))
        else:
            files.append(path)
    return files


def ingest_files(files: list[Path], on_conflict: str = "error") -> int:
    """Ingest từng file; file lỗi chỉ bị bỏ qua và báo ra stderr. Trả về số file lỗi."""
    failures = 0
    for path in files:
        try:
            file = load_quotation_file(path)
            with SessionLocal() as session:
                result = ingest_quotation(session, file, path.name, on_conflict=on_conflict)
            print(f"{path.name}: {json.dumps(dataclasses.asdict(result), ensure_ascii=False)}")
        except QuotationFileError as exc:
            failures += 1
            print(f"{path.name}: file không hợp lệ", file=sys.stderr)
            for error in exc.errors:
                print(f"  - {error}", file=sys.stderr)
        except DuplicateProjectError as exc:
            failures += 1
            print(f"{path.name}: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 -- lỗi DB bất ngờ: báo rồi đi tiếp file sau
            failures += 1
            print(f"{path.name}: lỗi khi ghi DB: {exc}", file=sys.stderr)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="nhập file báo giá YAML vào DB")
    ingest.add_argument("paths", nargs="+")
    ingest.add_argument(
        "--replace", action="store_true",
        help="nếu đã có công trình cùng tên nhưng nội dung khác thì thay thế toàn bộ (mặc định: báo lỗi)",
    )
    args = parser.parse_args(argv)

    init_db()
    failures = ingest_files(_collect(args.paths), on_conflict="replace" if args.replace else "error")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
