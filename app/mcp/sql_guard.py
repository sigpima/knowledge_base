"""Rào chắn cho tool `run_readonly_sql`: chỉ một câu SELECT/WITH, và luôn giới hạn số dòng.

Đây là lớp phòng thủ thứ nhất; chốt chặn thật là role Postgres chỉ đọc (`default_transaction_read_only`) cùng
`statement_timeout`, nên một câu lọt qua đây vẫn không ghi được dữ liệu.
"""
import re

# Mỗi mẫu khớp một "vùng không phải mã SQL": chú thích, chuỗi, định danh trong ngoặc kép, dollar-quote.
_NON_CODE = re.compile(
    r"""
    --[^\n]*                      # chú thích đến hết dòng
    | /\*.*?\*/                   # chú thích khối
    | '(?:[^']|'')*'              # chuỗi '...' (nhân đôi dấu nháy để thoát)
    | "(?:[^"]|"")*"              # định danh "..."
    | (\$[A-Za-z_]*\$).*?\1       # dollar-quote $$...$$ hoặc $tag$...$tag$
    """,
    re.DOTALL | re.VERBOSE,
)
_WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|merge|call|do|vacuum|set|reset)\b",
    re.IGNORECASE,
)


def _mask(query: str) -> str:
    """Thay mọi vùng không phải mã SQL bằng khoảng trắng, để chỉ còn lại phần mã cần kiểm tra."""
    return _NON_CODE.sub(" ", query)


def _strip(query: str) -> str:
    return query.strip().rstrip(";").strip()


def validate_select_only(query: str) -> None:
    code = _strip(_mask(query)).strip()
    if not code:
        raise ValueError("Query must not be empty.")

    if ";" in code:
        raise ValueError("Only a single SQL statement is allowed.")

    if not re.match(r"(?is)^(select|with)\b", code):
        raise ValueError("Only SELECT statements are allowed.")

    keyword = _WRITE_KEYWORDS.search(code)
    if keyword:
        raise ValueError(f"Statements that change data or settings are not allowed ({keyword.group(0).upper()}).")


def ensure_limit(query: str, default_limit: int = 200) -> str:
    """Bọc câu truy vấn trong một SELECT ngoài có LIMIT, bất kể trong câu gốc có chữ "limit" hay không.

    Có xuống dòng trước dấu đóng ngoặc để chú thích `--` ở cuối câu gốc không nuốt mất `)`.
    """
    return f"SELECT * FROM (\n{_strip(query)}\n) AS limited_query LIMIT {default_limit}"
