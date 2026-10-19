"""Tạo schema/bảng và role Postgres chỉ đọc cho MCP server.

    RO_PASSWORD=... python -m scripts.init_db

Mật khẩu role chỉ đọc lấy từ biến môi trường `RO_PASSWORD` (không bao giờ ghi cứng).
Chạy lại nhiều lần được: role đã có thì chỉ cập nhật mật khẩu và quyền.
"""
import os

from psycopg2 import sql
from sqlalchemy.engine import Engine

from app.infrastructure.database.postgres.session import engine, init_db

DEFAULT_ROLE = "knowledge_base_ro"


def ensure_readonly_role(target: Engine, role: str, password: str) -> None:
    raw = target.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        verb = "ALTER" if cursor.fetchone() else "CREATE"
        statements = [
            sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(sql.SQL(verb), sql.Identifier(role), sql.Literal(password)),
            sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(sql.Identifier(role)),
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(role)),
            sql.SQL("GRANT USAGE ON SCHEMA quotation TO {}").format(sql.Identifier(role)),
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA quotation TO {}").format(sql.Identifier(role)),
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA quotation GRANT SELECT ON TABLES TO {}").format(
                sql.Identifier(role)
            ),
        ]
        for statement in statements:
            cursor.execute(statement)
        raw.commit()
    finally:
        raw.close()


def main() -> None:
    password = os.environ.get("RO_PASSWORD")
    if not password:
        raise RuntimeError("Đặt biến môi trường RO_PASSWORD (mật khẩu cho role chỉ đọc của MCP server)")
    init_db()
    role = os.environ.get("RO_ROLE", DEFAULT_ROLE)
    ensure_readonly_role(engine, role, password)
    print(f"Đã sẵn sàng schema quotation và role chỉ đọc {role!r}")


if __name__ == "__main__":
    main()
