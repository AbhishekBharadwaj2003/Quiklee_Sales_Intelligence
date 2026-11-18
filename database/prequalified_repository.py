"""Persistence helpers for manually pre-qualified brand uploads.

This repository deliberately does not call TabAPI or any external traffic service.
Uploaded visitor counts are stored as user-supplied, previously researched figures.
"""
import json
from database.db import get_db
from database.company_repository import get_company_by_domain, get_all_companies, add_company, update_company
from database.campaign_repository import normalize_brand_key, normalize_domain, parse_visitor_count
from discovery.deduplication import normalize_company_name


def _find_company(name, website):
    domain = normalize_domain(website)
    if domain:
        found = get_company_by_domain(domain)
        if found:
            return found
    key = normalize_brand_key(name)
    for company in get_all_companies():
        if normalize_brand_key(company.get("company_nadef import_prequalified_brands(dataframe, brand_column, website_column, visitors_column, import_batch=''):
    """Insert/reuse companies and persist pre-qualified upload rows; no API calls."""
    if dataframe is None or dataframe.empty:
        raise ValueError("The uploaded dataset is empty.")
    if not brand_column or brand_column not in dataframe.columns:
        raise ValueError("Select a valid brand/company column.")
    if not visitors_column or visitors_column not in dataframe.columns:
        raise ValueError("Select a monthly visitors column.")

    imported, reused, skipped, below_threshold = 0, 0, 0, 0
    errors = []
    pending_records = []

    # Fetch existing companies once. Previously, each row could trigger repeated
    # full-company scans during matching and insertion.
    existing_companies = get_all_companies()
    companies_by_domain = {}
    companies_by_name = {}
    for existing in existing_companies:
        domain_key = normalize_domain(existing.get("website_url") or existing.get("domain") or "")
        name_key = normalize_company_name(existing.get("company_name") or "")
        if domain_key:
            companies_by_domain[domain_key] = existing
        if name_key:
            companies_by_name[name_key] = existing

    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=1):
        name = str(row.get(brand_column) or "").strip()
        website = str(row.get(website_column) or "").strip() if website_column else ""
        domain = normalize_domain(website) if website else ""
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

        name_key = normalize_company_name(name)
        company = companies_by_domain.get(domain) if domain else None
        if not company and name_key:
            company = companies_by_name.get(name_key)

        if company:
            company_id = company["id"]
            updates = {"validation_status": "prequalified_manual"}
            if website and not company.get("website_url"):
                updates["website_url"] = website
            update_company(company_id, updates)
            reused += 1
            # Keep in-memory maps current for duplicates later in this same upload.
            if domain:
                companies_by_domain[domain] = company
            if name_key:
                companies_by_name[name_key] = company
        else:
            # Insert directly instead of calling add_company(), which scans the
            # companies table for every new row. This preserves the same fields
            # and manual qualification status.
            with get_db() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO companies (company_name, website_url, domain, validation_status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, website, domain or None, "prequalified_manual"),
                )
                company_id = cursor.lastrowid
            if not company_id:
                errors.append(f"Row {row_number} ({name}): could not create company record.")
                skipped += 1
                continue
            company = {
                "id": company_id,
                "company_name": name,
                "website_url": website,
                "domain": domain or None,
                "validation_status": "prequalified_manual",
            }
            if domain:
                companies_by_domain[domain] = company
            if name_key:
                companies_by_name[name_key] = company
            imported += 1

        pending_records.append((
            company_id, name, website, visits, row_number,
            json.dumps(row.to_dict(), ensure_ascii=False, default=str),
            import_batch,
        ))

    # Save the upload records in one batch/transaction instead of opening a
    # database connection and committing separately for every row.
    if pending_records:
        with get_db() as connection:
            connection.executemany(
                """
                INSERT INTO prequalified_upload_records
                    (company_id, company_name, website, monthly_visitors, source_row_number, original_row_json, import_batch)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                pending_records,
            )

    return {
        "imported_companies": imported,
        "reused_companies": reused,
        "saved_records": imported + reused,
        "skipped_rows": skipped,
        "excluded_below_threshold": below_threshold,
        "errors": errors,
    }reshold": below_threshold,
        "errors": errors,
    }


def get_prequalified_import_batches():
    """List saved pre-qualified dataset batches."""
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT import_batch, COUNT(DISTINCT company_id) AS brand_count,
                   MAX(created_at) AS imported_at
            FROM prequalified_upload_records
            WHERE COALESCE(import_batch, '') != ''
            GROUP BY import_batch
            ORDER BY MAX(created_at) DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_prequalified_import_batch(import_batch):
    """Delete one saved dataset batch, preserving shared company profiles."""
    if not import_batch:
        return 0
    with get_db() as connection:
        cursor = connection.execute(
            "DELETE FROM prequalified_upload_records WHERE import_batch = ?",
            (import_batch,),
        )
        return cursor.rowcount


def get_prequalified_companies(import_batch=None):
    with get_db() as connection:
        if import_batch:
            rows = connection.execute(
                """
                SELECT c.*, MAX(p.monthly_visitors) AS prequalified_monthly_visitors,
                       MAX(p.created_at) AS prequalified_imported_at
                FROM prequalified_upload_records p
                JOIN companies c ON c.id = p.company_id
                WHERE p.import_batch = ?
                GROUP BY c.id
                ORDER BY MAX(p.created_at) DESC, c.company_name
                """,
                (import_batch,),
            ).fetchall()
        else:
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
