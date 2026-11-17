import os
import re
import sqlite3
from pathlib import Path
from contextlib import contextmanager


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "quiklee_sales.db"


def _get_database_url():
    """Read the PostgreSQL URL from environment variables or Streamlit Secrets."""
    value = os.getenv("DATABASE_URL")
    if value:
        return value.strip()

    try:
        import streamlit as st
        value = st.secrets.get("DATABASE_URL")
        if value:
            return str(value).strip()
    except Exception:
        # Streamlit is optional when running locally.
        pass

    return None


class _PostgresCursor:
    """Small SQLite-compatible cursor adapter for existing repository code."""

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self._cached_row = None
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        if self._cached_row is not None:
            row = self._cached_row
            self._cached_row = None
            return row
        return self._cursor.fetchone()

    def fetchall(self):
        rows = self._cursor.fetchall()
        if self._cached_row is not None:
            rows.insert(0, self._cached_row)
            self._cached_row = None
        return rows

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        if self._cached_row is not None:
            rows.insert(0, self._cached_row)
            self._cached_row = None
        return rows

    def __iter__(self):
        if self._cached_row is not None:
            yield self._cached_row
            self._cached_row = None
        yield from self._cursor


class _PostgresConnection:
    """Connection adapter that preserves the existing SQLite-style API."""

    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _adapt_placeholders(sql):
        # Existing SQL uses SQLite's '?' placeholders. Repository queries do
        # not use question marks inside SQL string literals.
        return sql.replace("?", "%s")

    @staticmethod
    def _adapt_ddl(sql):
        sql = re.sub(
            r"INTEGER\\s+PRIMARY\\s+KEY\\s+AUTOINCREMENT",
            "BIGSERIAL PRIMARY KEY",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(r"\\bINTEGER\\b", "BIGINT", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\\bREAL\\b", "DOUBLE PRECISION", sql, flags=re.IGNORECASE)
        return sql

    def execute(self, sql, parameters=None):
        statement = sql.strip()
        is_ddl = statement.upper().startswith(
            ("CREATE TABLE", "CREATE INDEX", "ALTER TABLE", "DROP TABLE", "DROP INDEX")
        )
        if is_ddl:
            statement = self._adapt_ddl(statement)
        else:
            statement = self._adapt_placeholders(statement)

        is_insert = bool(re.match(r"^INSERT\\s+INTO\\s+", statement, re.IGNORECASE))
        has_returning = bool(re.search(r"\\bRETURNING\\b", statement, re.IGNORECASE))
        if is_insert and not has_returning:
            statement = statement.rstrip().rstrip(";") + " RETURNING id"

        cursor = self._connection.cursor()
        cursor.execute(statement, parameters or ())

        lastrowid = None
        adapter = _PostgresCursor(cursor)
        if is_insert and not has_returning:
            row = cursor.fetchone()
            if row is not None:
                lastrowid = row.get("id") if isinstance(row, dict) else row[0]
                adapter._cached_row = row
            adapter.lastrowid = lastrowid

        return adapter

    def executemany(self, sql, parameter_rows):
        statement = self._adapt_placeholders(sql.strip())
        cursor = self._connection.cursor()
        cursor.executemany(statement, parameter_rows)
        return _PostgresCursor(cursor)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def get_connection():
    """Create a PostgreSQL connection when DATABASE_URL is configured.

    SQLite remains available for local development when DATABASE_URL is absent.
    """
    database_url = _get_database_url()
    if database_url:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL is configured but psycopg is not installed. "
                "Install dependencies from requirements.txt."
            ) from error

        connection = psycopg.connect(
            database_url,
            row_factory=dict_row,
            sslmode="require",
            connect_timeout=15,
        )
        return _PostgresConnection(connection)

    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def get_db():
    """Provide a managed database connection."""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create the application's core tables in PostgreSQL or local SQLite."""
    using_postgres = bool(_get_database_url())

    with get_db() as connection:
        if not using_postgres:
            connection.execute("PRAGMA foreign_keys = ON")

        connection.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                website_url TEXT,
                domain TEXT UNIQUE,
                category TEXT,
                description TEXT,
                headquarters TEXT,
                linkedin_url TEXT,
                company_size TEXT,
                validation_status TEXT DEFAULT 'pending',
                qualification_score REAL,
                qualification_category TEXT,
                data_completeness REAL DEFAULT 0,
                research_status TEXT DEFAULT 'pending',
                enrichment_status TEXT DEFAULT 'pending',
                first_discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_researched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS research_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                research_type TEXT NOT NULL,
                source TEXT,
                source_url TEXT,
                findings TEXT,
                confidence TEXT,
                researched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS company_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                event_type TEXT,
                event_title TEXT,
                event_description TEXT,
                amount REAL,
                currency TEXT,
                event_date TEXT,
                source_url TEXT,
                verification_status TEXT DEFAULT 'unverified',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS company_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                contact_name TEXT,
                designation TEXT,
                email TEXT,
                phone TEXT,
                linkedin_url TEXT,
                contact_source TEXT,
                enrichment_status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_name TEXT NOT NULL,
                source_filename TEXT,
                source_file_path TEXT,
                source_row_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'uploaded',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS campaign_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                source_row_number INTEGER NOT NULL,
                company_id INTEGER,
                source_brand_name TEXT,
                normalized_brand_key TEXT,
                original_row_json TEXT NOT NULL,
                website TEXT,
                monthly_visits REAL,
                traffic_status TEXT DEFAULT 'pending',
                research_status TEXT DEFAULT 'pending',
                lusha_status TEXT DEFAULT 'not_started',
                lead_score REAL,
                lead_category TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL,
                UNIQUE(campaign_id, source_row_number)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS contact_reveal_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_key TEXT NOT NULL,
                company_id INTEGER,
                field_type TEXT NOT NULL,
                reveal_status TEXT NOT NULL DEFAULT 'not_revealed',
                contact_id TEXT,
                revealed_value TEXT,
                credits_charged REAL DEFAULT 0,
                campaign_id INTEGER,
                attempted_at TIMESTAMP,
                revealed_at TIMESTAMP,
                error_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK(field_type IN ('email', 'phone')),
                UNIQUE(brand_key, field_type),
                FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_name ON companies(company_name)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_category ON companies(category)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_status ON companies(research_status)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_records_campaign
            ON campaign_records(campaign_id)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_records_company
            ON campaign_records(company_id)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_records_brand
            ON campaign_records(normalized_brand_key)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_reveal_ledger_brand
            ON contact_reveal_ledger(brand_key)
        """)

    if using_postgres:
        print("Quiklee PostgreSQL database initialized successfully.")
        print("Database backend: Supabase PostgreSQL")
    else:
        print("Quiklee SQLite database initialized successfully.")
        print(f"Database location: {DATABASE_PATH}")


if __name__ == "__main__":
    initialize_database()
