
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.company_repository import add_company
from database.research_repository import add_research_record


PRIORITY_FILE = PROJECT_ROOT / "data" / "lusha_company_priority.csv"
TRAFFIC_FILE = PROJECT_ROOT / "data" / "traffic_enrichment_results.csv"

DB_FILE = PROJECT_ROOT / "quiklee_sales.db"

RESEARCH_TYPE = "traffic_analysis"
TRAFFIC_SOURCE = "TabAPI"


def normalize_domain(value):
    if pd.isna(value):
        return ""

    domain = str(value).strip().lower()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.split("/")[0]
    domain = domain.removeprefix("www.")

    return domain


def parse_json_field(value):
    if pd.isna(value) or not str(value).strip():
        return None

    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def load_and_validate_data():
    if not PRIORITY_FILE.exists():
        raise FileNotFoundError(
            f"Priority file not found: {PRIORITY_FILE}"
        )

    if not TRAFFIC_FILE.exists():
        raise FileNotFoundError(
            f"Traffic file not found: {TRAFFIC_FILE}"
        )

    priority = pd.read_csv(PRIORITY_FILE)
    traffic = pd.read_csv(TRAFFIC_FILE)

    required_priority = {
        "company_name",
        "company_domain",
        "monthly_visits",
    }

    required_traffic = {
        "company_name",
        "domain",
        "monthly_visits",
        "reporting_month",
        "status",
        "credits_charged",
    }

    if not required_priority.issubset(priority.columns):
        raise ValueError(
            "Priority CSV is missing required columns."
        )

    if not required_traffic.issubset(traffic.columns):
        raise ValueError(
            "Traffic CSV is missing required columns."
        )

    priority["domain_key"] = priority[
        "company_domain"
    ].apply(normalize_domain)

    traffic["domain_key"] = traffic[
        "domain"
    ].apply(normalize_domain)

    if priority["domain_key"].duplicated().any():
        raise ValueError(
            "Duplicate company domains found in priority CSV."
        )

    if traffic["domain_key"].duplicated().any():
        raise ValueError(
            "Duplicate domains found in traffic CSV."
        )

    merged = priority.merge(
        traffic,
        on="domain_key",
        how="left",
        suffixes=("_priority", "_traffic"),
        validate="one_to_one",
    )

    if merged["status"].isna().any():
        missing = merged[
            merged["status"].isna()
        ]["company_name_priority"].tolist()

        raise ValueError(
            f"Missing TabAPI records for: {missing}"
        )

    if not merged["status"].eq("completed").all():
        raise ValueError(
            "One or more traffic records are not completed."
        )

    priority_visits = pd.to_numeric(
        merged["monthly_visits_priority"],
        errors="coerce",
    )

    traffic_visits = pd.to_numeric(
        merged["monthly_visits_traffic"],
        errors="coerce",
    )

    if priority_visits.isna().any() or traffic_visits.isna().any():
        raise ValueError(
            "Missing or invalid monthly visitor counts."
        )

    if not priority_visits.equals(traffic_visits):
        raise ValueError(
            "Priority visitor counts do not match TabAPI records."
        )

    if (traffic_visits < 100000).any():
        raise ValueError(
            "A company is below the 100,000 visitor threshold."
        )

    if not merged["reporting_month"].notna().all():
        raise ValueError(
            "A traffic reporting month is missing."
        )

    return merged


def build_findings(row):
    return {
        "source": "TabAPI",
        "domain": normalize_domain(row["domain"]),
        "monthly_visits": int(row["monthly_visits_traffic"]),
        "reporting_month": str(row["reporting_month"]),
        "global_rank": optional_number(row.get("global_rank")),
        "country_rank": optional_number(row.get("country_rank")),
        "bounce_rate": optional_number(row.get("bounce_rate")),
        "pages_per_visit": optional_number(
            row.get("pages_per_visit")
        ),
        "time_on_site_seconds": optional_number(
            row.get("time_on_site_seconds")
        ),
        "monthly_history": parse_json_field(
            row.get("monthly_history")
        ),
        "traffic_sources": parse_json_field(
            row.get("traffic_sources")
        ),
        "top_regions": parse_json_field(
            row.get("top_regions")
        ),
        "top_keywords": parse_json_field(
            row.get("top_keywords")
        ),
        "ai_traffic": parse_json_field(
            row.get("ai_traffic")
        ),
        "credits_charged": optional_number(
            row.get("credits_charged")
        ),
        "status": "completed",
        "traffic_threshold": 100000,
        "traffic_eligibility": "qualified",
    }


def optional_number(value):
    if pd.isna(value):
        return None

    try:
        number = float(value)

        if number.is_integer():
            return int(number)

        return number
    except (ValueError, TypeError):
        return None


def get_existing_reporting_months(company_id):
    import sqlite3

    connection = sqlite3.connect(DB_FILE)

    try:
        rows = connection.execute(
            """
            SELECT findings
            FROM research_history
            WHERE company_id = ?
              AND research_type = ?
              AND source = ?
            """,
            (company_id, RESEARCH_TYPE, TRAFFIC_SOURCE),
        ).fetchall()
    finally:
        connection.close()

    months = set()

    for (raw_findings,) in rows:
        try:
            findings = (
                json.loads(raw_findings)
                if isinstance(raw_findings, str)
                else raw_findings
            )

            if isinstance(findings, dict):
                month = findings.get("reporting_month")

                if month:
                    months.add(str(month))

        except (ValueError, TypeError):
            continue

    return months


def prepare_company(row):
    domain = normalize_domain(row["domain"])

    return {
        "company_name": str(row["company_name_priority"]).strip(),
        "website_url": f"https://{domain}",
        "category": None,
        "description": (
            "Company registered from the Quiklee "
            "Sales Intelligence prospecting dataset."
        ),
        "validation_status": "pending",
    }


def run_import(execute=False):
    data = load_and_validate_data()

    print("\n========== VERIFIED TRAFFIC IMPORT ==========")
    print(f"Companies found: {len(data)}")
    print("Traffic source: TabAPI")
    print("Reporting month(s):",
          ", ".join(sorted(data["reporting_month"].astype(str).unique())))
    print("External API calls: NONE")
    print("Mode:", "EXECUTE" if execute else "DRY RUN")

    imported = 0
    existing = 0
    new_companies = 0
    reused_companies = 0

    for _, row in data.iterrows():
        name = str(row["company_name_priority"]).strip()
        domain = normalize_domain(row["domain"])
        month = str(row["reporting_month"])
        visits = int(row["monthly_visits_traffic"])

        print(f"\n{name} | {domain}")
        print(f"Visitors: {visits:,} | Month: {month}")

        if not execute:
            print("DRY RUN: Would register company and save traffic.")
            continue

        company_result = add_company(prepare_company(row))

        if not company_result or not company_result.get("company_id"):
            raise RuntimeError(
                f"Could not register or find company: {name}"
            )

        company_id = company_result["company_id"]

        if company_result.get("success"):
            new_companies += 1
        else:
            reused_companies += 1

        existing_months = get_existing_reporting_months(
            company_id
        )

        if month in existing_months:
            print(
                f"SKIPPED: {month} TabAPI traffic already exists."
            )
            existing += 1
            continue

        findings = build_findings(row)

        add_research_record(
            company_id=company_id,
            research_type=RESEARCH_TYPE,
            source=TRAFFIC_SOURCE,
            findings=findings,
            source_url=None,
            confidence="verified",
        )

        print(f"IMPORTED: Company ID {company_id}")
        imported += 1

    print("\n========== IMPORT SUMMARY ==========")

    if execute:
        print("New companies:", new_companies)
        print("Existing companies reused:", reused_companies)
        print("Traffic records imported:", imported)
        print("Existing traffic records skipped:", existing)
    else:
        print("Companies ready for import:", len(data))
        print("No database changes were made.")
        print(
            "\nTo execute, run this script with --execute."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import existing verified TabAPI traffic records."
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write companies and traffic records to SQLite.",
    )

    args = parser.parse_args()

    run_import(execute=args.execute)
