
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
    """Create initial and campaign-related database tables."""

    with get_db() as connection:

        # Existing main company records
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

        # Existing research history
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

        # Existing funding and growth records
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

        # Existing contact information
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

        # NEW: Every uploaded dataset becomes a campaign
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

        # NEW: Preserve every original spreadsheet row.
        # Duplicate brand rows are intentionally allowed.
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

                FOREIGN KEY(campaign_id)
                    REFERENCES campaigns(id)
                    ON DELETE CASCADE,

                FOREIGN KEY(company_id)
                    REFERENCES companies(id)
                    ON DELETE SET NULL,

                UNIQUE(campaign_id, source_row_number)
            )
        """)

        # NEW: Persistent brand-level reveal protection.
        # Email and phone have independent reveal restrictions.
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

                FOREIGN KEY(company_id)
                    REFERENCES companies(id)
                    ON DELETE SET NULL,

                FOREIGN KEY(campaign_id)
                    REFERENCES campaigns(id)
                    ON DELETE SET NULL
            )
        """)

        # Existing indexes
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

        # New campaign indexes
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

    print("Quiklee database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")


if __name__ == "__main__":
    initialize_database()
