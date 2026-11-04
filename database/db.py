
import sqlite3
from pathlib import Path
from contextlib import contextmanager


# Store database in the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = PROJECT_ROOT / "quiklee_sales.db"


def get_connection():
    """Create a database connection."""

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )

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
    """Create all initial database tables."""

    with get_db() as connection:

        # Main company records
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

        # Research history
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

                FOREIGN KEY(company_id)
                    REFERENCES companies(id)
                    ON DELETE CASCADE

            )
        """)

        # Funding and growth records
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

                FOREIGN KEY(company_id)
                    REFERENCES companies(id)
                    ON DELETE CASCADE

            )
        """)

        # Contact information
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

                FOREIGN KEY(company_id)
                    REFERENCES companies(id)
                    ON DELETE CASCADE

            )
        """)

        # Indexes for faster searches
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_name
            ON companies(company_name)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_category
            ON companies(category)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_status
            ON companies(research_status)
        """)

    print("Quiklee database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")


if __name__ == "__main__":
    initialize_database()
