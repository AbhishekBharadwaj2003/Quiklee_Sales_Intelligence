"""Persistence helpers for manually pre-qualified brand uploads.

This repository deliberately does not call TabAPI or any external traffic service.
Uploaded visitor counts are stored as user-supplied, previously researched figures.
"""
import json
from database.db import get_db
from database.company_repository import get_company_by_domain, get_all_companies, add_company, update_company
from database.campaign_repository import normalize_brand_key, normalize_domain, parse_visitor_count


def _find_company(name, website):
    domain = normalize_domain(website)
    if domain:
        found = get_company_by_domain(domain)
        if found:
            return found
    key = normalize_brand_key(name)
    for company in get_all_companies():
        if normalize_brand_key(company.get("company_name")) == key:
            return company
    return None


def import_prequalified_brands(dataframe, brand_column, website_column, visitors_column):
    """Insert/reuse companies and persist pre-qualified upload rows; no API calls."""
    if dataframe is None or dataframe.empty:
        raise ValueError("The uploaded dataset is empty.")
    if not brand_column or brand_column not in dataframe.columns:
        raise ValueError("Select a valid brand/company column.")
    if not visitors_column or visitors_column not in dataframe.columns:
        raise ValueError("Select a monthly visitors column.")

    imported, reused, skipped, below_threshold = 0, 0, 0, 0
    errors = []
    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=1):
        name = str(row.get(brand_column) or "").strip()
        website = str(row.get(website_column) or "").strip() if website_column else ""
        visits = parse_visitor_count(row.get(visitors_column))
        if not name:
            skipped += 1
            continue
        if visits is None:
            errors.append(f"Row {row_number}: monthly visitors is missing or invalid.")
            skipped += 1
            continue
        if visits <= 100000:
            below_threshold += 1
            errors.append(f"Row {row_number} ({name}): {visits:,.0f} visitors is not above 100,000; excluded.")
            continue

        company = _find_company(name, website)
        if company:
            company_id = company["id"]
            updates = {}
            if website and not company.get("website_url"):
                updates["website_url"] = website
            # Mark as qualified based on the user's prior manual research.
            # This remains an imported/manual status, not a TabAPI result.
            updates["validation_status"] = "prequalified_manual"
            if updates:
                update_company(company_id, updates)
            reused += 1
        else:
            result = add_company({
                "company_name": name,
                "website_url": website,
                "validation_status": "prequalified_manual",
            })
            company_id = result.get("company_id")
            if not company_id:
                errors.append(f"Row {row_number} ({name}): could not create company record.")
                skipped += 1
                continue
            update_company(company_id, {"validation_status": "prequalified_manual"})
            imported += 1

        with get_db() as connection:
            connection.execute(
                """
                INSERT INTO prequalified_upload_records
                    (company_id, company_name, website, monthly_visitors, source_row_number, original_row_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, name, website, visits, row_number,
                    json.dumps(row.to_dict(), ensure_ascii=False, default=str),
                ),
            )

    return {
        "imported_companies": imported,
        "reused_companies": reused,
        "saved_records": imported + reused,
        "skipped_rows": skipped,
        "excluded_below_threshold": below_threshold,
        "errors": errors,
    }


def get_prequalified_companies():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT c.*, MAX(p.monthly_visitors) AS prequalified_monthly_visitors,
                   MAX(p.created_at) AS prequalified_imported_at
            FROM prequalified_upload_records p
            JOIN companies c ON c.id = p.company_id
            GROUP BY c.id
            ORDER BY MAX(p.created_at) DESC, c.company_name
            """
        ).fetchall()
    return [dict(row) for row in rows]
