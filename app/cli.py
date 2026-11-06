"""Dòng lệnh: `python -m app.cli ingest PATH [PATH...]` (PATH là file hoặc thư mục chứa *.yaml)
và `python -m app.cli ingest-policies PATH [PATH...] [--prune]` (PATH là file hoặc thư mục chứa *.md)."""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

from app.domains.policy.application.services.corpus import PolicyDocument, PolicyFileError, load_policy_file
from app.domains.policy.application.services.ingest import ingest_policy, prune_policies
from app.domains.policy.infrastructure.embedding.base import EmbeddingError, EmbeddingNotConfiguredError
from app.domains.policy.infrastructure.vectorstore.base import PolicyStoreError, PolicyStoreUnavailableError
from app.domains.quotation.application.services.ingest.loader import QuotationFileError, load_quotation_file
from app.domains.quotation.application.services.ingest.writer import DuplicateProjectError, ingest_quotation
from app.infrastructure.config.config import settings
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


class PolicyPathError(ValueError):
    """PATH của `ingest-policies` không dùng được (không tồn tại, hoặc thư mục không có *.md)."""


def _collect_policy_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found = sorted(path.glob("*.md"), key=lambda p: p.name)
            if not found:
                raise PolicyPathError(f"thư mục {raw} không có file *.md nào")
        elif path.is_file():
            found = [path]
        else:
            raise PolicyPathError(f"không tìm thấy {raw}")
        for file in found:
            key = file.resolve()
            if key not in seen:
                seen.add(key)
                files.append(file)
    return files


def _load_policies(files: list[Path]) -> tuple[list[PolicyDocument], int]:
    """Đọc từng file; file hỏng hoặc trùng slug (file đứng trước thắng) chỉ báo stderr. Trả (tài liệu, số lỗi)."""
    documents: list[PolicyDocument] = []
    first_seen: dict[str, str] = {}
    failures = 0
    for path in files:
        try:
            document = load_policy_file(path)
        except PolicyFileError as exc:
            failures += 1
            print(f"{path.name}: file không hợp lệ", file=sys.stderr)
            for error in exc.errors:
                print(f"  - {error}", file=sys.stderr)
            continue
        slug = document.front.slug
        if slug in first_seen:
            failures += 1
            print(f"{path.name}: slug {slug!r} đã dùng ở {first_seen[slug]}, bỏ qua file này", file=sys.stderr)
            continue
        first_seen[slug] = path.name
        documents.append(document)
    return documents, failures


def ingest_policies(paths: list[str], prune: bool = False) -> int:
    """Nạp tài liệu chính sách vào Milvus. Mã thoát: 0 tốt, 1 có file lỗi, 2 lỗi cấu hình/PATH (chưa ghi gì)."""
    try:
        files = _collect_policy_files(paths)
    except PolicyPathError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    documents, failures = _load_policies(files)
    if not documents:
        return 1

    # Import muộn: `google-genai` chỉ có trong requirements-chat.txt, lệnh `ingest` không được phụ thuộc vào nó.
    try:
        from app.domains.policy.infrastructure.embedding.gemini import build_embedder
        from app.domains.policy.infrastructure.vectorstore.milvus_store import build_milvus_store
    except ImportError:
        print(
            "Lỗi: thiếu gói cần thiết để nạp chính sách (google-genai, pymilvus); "
            "cài requirements.txt và requirements-chat.txt rồi chạy lại.",
            file=sys.stderr,
        )
        return 2

    try:
        embedder = build_embedder(settings.gemini_api_key, settings.gemini_embedding_model, settings.gemini_base_url)
    except EmbeddingNotConfiguredError:
        print("Lỗi: chưa đặt GEMINI_API_KEY nên không tạo được embedding.", file=sys.stderr)
        return 2
    store = build_milvus_store(settings.milvus_uri, settings.milvus_token, settings.milvus_collection)
    try:
        store.ensure_collection()
    except PolicyStoreUnavailableError:
        print("Lỗi: không kết nối được Milvus (kiểm tra MILVUS_URI và MILVUS_TOKEN).", file=sys.stderr)
        return 2
    except PolicyStoreError as exc:
        print(f"Lỗi: không chuẩn bị được collection chính sách: {exc}", file=sys.stderr)
        return 2

    for document in documents:
        try:
            result = ingest_policy(store, embedder, document)
            print(f"{result.slug}: {json.dumps(dataclasses.asdict(result), ensure_ascii=False)}")
        except (EmbeddingError, PolicyStoreError) as exc:
            failures += 1
            print(f"{document.source_name}: lỗi khi nạp: {exc}", file=sys.stderr)

    if prune:
        if failures:
            print("Có file lỗi nên không xoá tài liệu cũ (--prune bị bỏ qua).", file=sys.stderr)
        else:
            try:
                for slug in prune_policies(store, {document.front.slug for document in documents}):
                    print(f"{slug}: đã xoá (không còn trong nguồn)")
            except PolicyStoreError as exc:
                failures += 1
                print(f"Lỗi khi xoá tài liệu cũ: {exc}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="nhập file báo giá YAML vào DB")
    ingest.add_argument("paths", nargs="+")
    ingest.add_argument(
        "--replace", action="store_true",
        help="nếu đã có công trình cùng tên nhưng nội dung khác thì thay thế toàn bộ (mặc định: báo lỗi)",
    )
    policies = sub.add_parser("ingest-policies", help="nạp tài liệu chính sách (Markdown) vào Milvus")
    policies.add_argument("paths", nargs="+")
    policies.add_argument(
        "--prune", action="store_true",
        help="xoá khỏi Milvus tài liệu không còn trong PATH (chỉ chạy khi mọi file đều nạp được)",
    )
    args = parser.parse_args(argv)

    if args.command == "ingest-policies":
        return ingest_policies(args.paths, prune=args.prune)

    init_db()
    failures = ingest_files(_collect(args.paths), on_conflict="replace" if args.replace else "error")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
