-- scripts/create_readonly_role.sql
-- One-time manual setup for the MCP query server's `run_readonly_sql` tool.
-- Run once per Postgres instance, passing the role's password as a psql
-- variable (never commit a literal password to this file):
--   psql -v ro_password='your-password-here' -f scripts/create_readonly_role.sql -d knowledge_base
--
-- This role is intentionally separate from the app's write-capable role:
-- the MCP server only ever connects with this read-only one.

CREATE ROLE knowledge_base_ro LOGIN PASSWORD :'ro_password';
GRANT USAGE ON SCHEMA quotation TO knowledge_base_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA quotation TO knowledge_base_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA quotation GRANT SELECT ON TABLES TO knowledge_base_ro;
ALTER ROLE knowledge_base_ro SET statement_timeout = '5s';
