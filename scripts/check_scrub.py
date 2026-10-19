"""Quét repo tìm từ khoá không được phép xuất hiện trong bản public.

Chạy `python scripts/check_scrub.py` trước mỗi commit; thoát mã 1 nếu có khớp.

Danh sách mặc định chỉ gồm thứ chung chung (thương hiệu bên thứ ba, đường dẫn
cá nhân, nhà cung cấp dịch vụ không còn dùng). Từ khoá riêng cần giữ kín (tên
công ty cũ, tên người dùng cũ...) nằm trong file cục bộ `.scrub-patterns`
(mỗi dòng một regex, không phân biệt hoa thường, dòng bắt đầu bằng `#` là chú
thích). File đó bị git bỏ qua nên không bao giờ lên GitHub.
"""
import re
import sys
from pathlib import Path

DEFAULT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\blark\b",
        r"sharepoint",
        r"dulux",
        r"jotun",
        r"nippon",
        r"mykolor",
        r"bạch tuyết",
        r"/home/[a-z]",
        r"/Users/[A-Za-z]",
    )
] + [re.compile(p) for p in (r"\bTOA\b", r"\bSika\b", r"\bSpec\b")]

PATTERNS_FILE_NAME = ".scrub-patterns"
SKIP_DIRS = {".git", ".venv", "venv", ".superpowers", "__pycache__", ".pytest_cache", "node_modules"}
# Hai file này nhắc từ khoá cấm vì chính chúng định nghĩa danh sách cấm.
SELF_FILES = {"scripts/check_scrub.py", "tests/test_scrub.py", PATTERNS_FILE_NAME}


def load_patterns(patterns_file: Path | None = None) -> list[re.Pattern]:
    patterns = list(DEFAULT_PATTERNS)
    if patterns_file is not None and Path(patterns_file).is_file():
        for raw in Path(patterns_file).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                patterns.append(re.compile(line, re.IGNORECASE))
    return patterns


def _match(text: str, patterns: list[re.Pattern]) -> str | None:
    for pattern in patterns:
        found = pattern.search(text)
        if found:
            return found.group(0)
    return None


def scan(root: Path, patterns_file: Path | None = None) -> list[tuple[Path, int, str]]:
    """Trả về danh sách (file, số dòng, chuỗi khớp); số dòng là 0 khi khớp ở tên file.

    Mặc định đọc thêm `<root>/.scrub-patterns` nếu có.
    """
    root = Path(root)
    if patterns_file is None:
        patterns_file = root / PATTERNS_FILE_NAME
    patterns = load_patterns(patterns_file)
    hits: list[tuple[Path, int, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts) or not path.is_file():
            continue
        if relative.as_posix() in SELF_FILES:
            continue
        name_hit = _match(relative.as_posix(), patterns)
        if name_hit:
            hits.append((path, 0, name_hit))
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            line_hit = _match(line, patterns)
            if line_hit:
                hits.append((path, number, line_hit))
    return hits


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    if not (root / PATTERNS_FILE_NAME).is_file():
        print(f"Cảnh báo: chưa có {PATTERNS_FILE_NAME}; chỉ quét danh sách mặc định.", file=sys.stderr)
    hits = scan(root)
    for path, number, found in hits:
        print(f"{path.relative_to(root)}:{number}: {found}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
