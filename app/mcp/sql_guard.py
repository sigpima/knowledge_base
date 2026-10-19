import re


def validate_select_only(query: str) -> None:
    stripped = query.strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("Query must not be empty.")

    if ";" in stripped:
        raise ValueError("Only a single SQL statement is allowed.")

    if not re.match(r"(?is)^select\b", stripped):
        raise ValueError("Only SELECT statements are allowed.")


def ensure_limit(query: str, default_limit: int = 200) -> str:
    stripped = query.strip().rstrip(";").strip()
    if re.search(r"(?is)\blimit\b", stripped):
        return stripped
    return f"{stripped} LIMIT {default_limit}"
