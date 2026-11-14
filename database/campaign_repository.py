
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from database.db import get_db
from discovery.deduplication import normalize_company_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAFFIC_FILE = PROJECT_ROOT / "data" / "traffic_enrichment_results.csv"
TRAFFIC_THRESHOLD = 100000


def normalize_brand_key(name):
    """Create a consistent brand identity key."""

    if name is None or pd.isna(name):
        return ""

    return normalize_company_name(str(name))


def normalize_domain(value):
    """Normalize a website or domain into a comparable domain."""

    if value is None or pd.isna(value):
        return ""

    value = str(value).strip().lower()

    if not value:
        return ""

    if not value.startswith(("http://", "https://")):
        value = "https://" + value

    domain = urlparse(value).netloc.lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def parse_visitor_count(value):
    """Convert visitor counts such as 1.01M, 250K or 100,000 into numbers."""

    if value is None or pd.isna(value):
        return None

    cleaned = re.sub(r"[,\\s]", "", str(value).strip()).upper()

    if not cleaned:
        return None

    multiplier = 1
    if cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]

    try:
        number = float(cleaned) * multiplier
        return number if number >= 0 else None
    except (ValueError, TypeError):
        return None

def load_existing_traffic():
    """
    Load completed traffic results into domain and brand lookups.

    This function only reads the existing CSV.
    It does not make API requests.
    """

    domain_lookup = {}
    brand_lookup = {}

    if not TRAFFIC_FILE.exists():
        return domain_lookup, brand_lookup

    try:
        traffic_df = pd.read_csv(TRAFFIC_FILE)
    except Exception:
        return domain_lookup, brand_lookup

    required_columns = {
        "company_name",
        "domain",
        "monthly_visits",
        "status",
    }

    if not required_columns.issubset(traffic_df.columns):
        return domain_lookup, brand_lookup

    for _, row in traffic_df.iterrows():

        if str(row.get("status", "")).strip().lower() != "completed":
            continue

        visits = parse_visitor_count(row.get("monthly_visits"))

        if visits is None:
            continue

        domain = normalize_domain(row.get("domain"))
        brand_key = normalize_brand_key(row.get("company_name"))

        traffic_record = {
            "monthly_visits": visits,
            "reporting_month": row.get("reporting_month"),
            "domain": domain,
        }

        if domain:
            domain_lookup[domain] = traffic_record

        if brand_key:
            brand_lookup[brand_key] = traffic_record

    return domain_lookup, brand_lookup


def classify_traffic(monthly_visitors):
    """Apply the campaign's minimum traffic qualification rule."""

    if monthly_visitors is None:
        return "pending"

    if monthly_visitors >= TRAFFIC_THRESHOLD:
        return "qualified"

    return "below_threshold"


def create_campaign(
    dataframe,
    campaign_name,
    source_filename,
    column_mapping,
    source_file_path=None,
):
    """
    Save an uploaded dataset as a campaign.

    Every source row is preserved, including duplicate brands.

    Existing completed traffic results are reused locally.
    No external API calls are made.
    """

    if dataframe is None or dataframe.empty:
        raise ValueError("The uploaded dataset is empty.")

    brand_column = column_mapping.get("brand")
    website_column = column_mapping.get("website")
    traffic_column = column_mapping.get("monthly_visitors")

    if not brand_column or brand_column not in dataframe.columns:
        raise ValueError("A valid brand-name column is required.")

    if website_column and website_column not in dataframe.columns:
        website_column = None

    if traffic_column and traffic_column not in dataframe.columns:
        traffic_column = None

    domain_lookup, brand_lookup = load_existing_traffic()

    with get_db() as connection:

        cursor = connection.execute(
            """
            INSERT INTO campaigns (
                campaign_name,
                source_filename,
                source_file_path,
                source_row_count,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                campaign_name.strip(),
                source_filename,
                source_file_path,
                len(dataframe),
                "uploaded",
            ),
        )

        campaign_id = cursor.lastrowid

        saved_count = 0
        skipped_count = 0
        reused_traffic_count = 0
        uploaded_traffic_count = 0

        for source_row_number, (_, row) in enumerate(
            dataframe.iterrows(),
            start=1,
        ):

            brand_name = row.get(brand_column)

            if brand_name is None or pd.isna(brand_name):
                skipped_count += 1
                continue

            brand_name = str(brand_name).strip()

            if not brand_name:
                skipped_count += 1
                continue

            brand_key = normalize_brand_key(brand_name)

            website = ""

            if website_column:
                value = row.get(website_column)

                if value is not None and not pd.isna(value):
                    website = str(value).strip()

            domain = normalize_domain(website)

            # First preference: visitor count supplied in the upload.
            monthly_visitors = None

            if traffic_column:
                monthly_visitors = parse_visitor_count(
                    row.get(traffic_column)
                )

            if monthly_visitors is not None:
                uploaded_traffic_count += 1

            else:
                # Second preference: match existing traffic by domain.
                traffic_record = (
                    domain_lookup.get(domain) if domain else None
                )

                # Fallback: match by normalized brand name.
                if traffic_record is None:
                    traffic_record = brand_lookup.get(brand_key)

                if traffic_record is not None:
                    monthly_visitors = traffic_record["monthly_visits"]
                    reused_traffic_count += 1

            traffic_status = classify_traffic(monthly_visitors)

            original_row = {}

            for key, value in row.to_dict().items():

                if value is None:
                    original_row[str(key)] = None
                    continue

                try:
                    missing = pd.isna(value)
                    if isinstance(missing, bool) and missing:
                        original_row[str(key)] = None
                        continue
                except (TypeError, ValueError):
                    pass

                original_row[str(key)] = value

            connection.execute(
                """
                INSERT INTO campaign_records (
                    campaign_id,
                    source_row_number,
                    source_brand_name,
                    normalized_brand_key,
                    original_row_json,
                    website,
                    monthly_visits,
                    traffic_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    source_row_number,
                    brand_name,
                    brand_key,
                    json.dumps(
                        original_row,
                        ensure_ascii=False,
                        default=str,
                    ),
                    website,
                    monthly_visitors,
                    traffic_status,
                ),
            )

            saved_count += 1

        connection.execute(
            """
            UPDATE campaigns
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                "processed" if saved_count else "empty",
                campaign_id,
            ),
        )

    return {
        "success": True,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "total_source_rows": len(dataframe),
        "saved_rows": saved_count,
        "skipped_rows": skipped_count,
        "uploaded_traffic_rows": uploaded_traffic_count,
        "reused_traffic_rows": reused_traffic_count,
    }


def get_all_campaigns():
    """Retrieve all campaigns, newest first."""

    with get_db() as connection:

        rows = connection.execute(
            """
            SELECT
                c.*,
                COUNT(r.id) AS saved_records
            FROM campaigns c
            LEFT JOIN campaign_records r
                ON c.id = r.campaign_id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]


def get_campaign_records(campaign_id):
    """Retrieve every saved row belonging to a campaign."""

    with get_db() as connection:

        rows = connection.execute(
            """
            SELECT *
            FROM campaign_records
            WHERE campaign_id = ?
            ORDER BY source_row_number
            """,
            (campaign_id,),
        ).fetchall()

        return [dict(row) for row in rows]



def delete_campaign(campaign_id):
    """Delete a campaign and its uploaded row records, preserving shared companies."""
    with get_db() as connection:
        cursor = connection.execute("DELETE FROM campaigns WHERE id = ?", (int(campaign_id),))
        return cursor.rowcount > 0
