"""
Centralized psycopg2 connection for Brain2 pgvector queries + Worker.
Reads credentials from engine.config — never hardcodes secrets.
"""
import psycopg2
from engine.config import (
    SUPABASE_DB_HOST,
    SUPABASE_DB_PORT,
    SUPABASE_DB_NAME,
    SUPABASE_DB_USER,
    SUPABASE_DB_PASSWORD,
)

_conn = None


def get_pg_conn():
    """Return a psycopg2 connection to Supabase Postgres (pgvector pooler)."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=SUPABASE_DB_HOST,
            port=SUPABASE_DB_PORT,
            dbname=SUPABASE_DB_NAME,
            user=SUPABASE_DB_USER,
            password=SUPABASE_DB_PASSWORD,
            sslmode="require",
        )
    return _conn
