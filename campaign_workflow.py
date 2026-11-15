from io import BytesIO
from urllib.parse import urlparse

import pandas as pd

from database.db import get_db
from database.company_repository import get_company_by_id, update_company
from database.research_repository import add_research_record
from database.research_repository import get_company_research_history
from research.traffic_analysis import analyse_traffic
from qualification.qualification_pipeline import qualify_company
from research.research_pipeline import run_company_research


TRAFFIC_THRESHOLD = 100000


def _normalise_domain(website):
    """Convert a website URL or bare domain into a clean domain."""
    value = str(website or "").strip()
    if not value:
        return ""

    if not value.startswith(("http://", "https://")):
        value = "https://" + value

    domain = urlparse(value).netloc.lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def get_campaign_traffic_candidates(campaign_id):
    """
    Return one selectable entry per unique company that still needs
    TabAPI traffic validation. This function never calls an external API.
    """
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT
                cr.company_id,
                cr.source_brand_name,
                cr.website,
                cr.monthly_visits,
                cr.traffic_status,
                c.company_name,
                c.website_url
            FROM campaign_records cr
            LEFT JOIN companies c ON c.id = cr.company_id
            WHERE cr.campaign_id = ?
              AND cr.company_id IS NOT NULL
            ORDER BY cr.source_row_number
            """,
            (campaign_id,),
        ).fetchall()

    candidates = {}

    for row in rows:
        item = dict(row)
        company_id = item["company_id"]

        if company_id not in candidates:
            website = item.get("website") or item.get("website_url") or ""
            candidates[company_id] = {
                "company_id": company_id,
                "company_name": (
                    item.get("source_brand_name")
                    or item.get("company_name")
                    or "Unknown company"
                ),
                "website": website,
                "domain": _normalise_domain(website),
                "monthly_visits": item.get("monthly_visits"),
                "traffic_status": item.get("traffic_status") or "pending",
            }
        else:
            # Prefer a row with a usable website if the first duplicate lacked one.
            if not candidates[company_id]["website"]:
                website = item.get("website") or item.get("website_url") or ""
                candidates[company_id]["website"] = website
                candidates[company_id]["domain"] = _normalise_domain(website)

    return [
        item
        for item in candidates.values()
        if item["traffic_status"] not in (
            "qualified",
            "below_threshold",
            "manual_review",
        )
    ]


def run_single_company_traffic_validation(campaign_id, company_id, months=3):
    """
    Validate exactly one selected company using TabAPI.

    This function makes at most one TabAPI request. A failed lookup remains
    pending and does not overwrite an earlier valid traffic result.
    """
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT
                cr.company_id,
                cr.source_brand_name,
                cr.website,
                cr.monthly_visits,
                cr.traffic_status,
                c.company_name,
                c.website_url
            FROM campaign_records cr
            LEFT JOIN companies c ON c.id = cr.company_id
            WHERE cr.campaign_id = ?
              AND cr.company_id = ?
            ORDER BY cr.source_row_number
            """,
            (campaign_id, company_id),
        ).fetchall()

    if not rows:
        raise ValueError("Selected company was not found in this campaign.")

    records = [dict(row) for row in rows]
    item = next(
        (
            record for record in records
            if record.get("website") or record.get("website_url")
        ),
        records[0],
    )

    company = get_company_by_id(company_id) or {}
    website = (
        item.get("website")
        or item.get("website_url")
        or company.get("website_url")
        or ""
    )
    company_name = (
        item.get("source_brand_name")
        or item.get("company_name")
        or company.get("company_name")
        or "Unknown company"
    )
    domain = _normalise_domain(website)

    if not domain:
        raise ValueError(
            f"An official website is missing for {company_name}."
        )

    existing_statuses = {
        str(record.get("traffic_status") or "").strip().lower()
        for record in records
    }

    if "qualified" in existing_statuses:
        raise ValueError(
            f"{company_name} has already passed traffic validation."
        )

    if "below_threshold" in existing_statuses:
        raise ValueError(
            f"{company_name} has already been classified below the threshold."
        )

    if "manual_review" in existing_statuses:
        raise ValueError(
            f"{company_name} requires manual review before validation."
        )

    if not company.get("website_url"):
        update_company(company_id, {"website_url": website})

    # Exactly one call to the TabAPI-backed traffic function.
    result = analyse_traffic(domain, months=months)

    visits = None
    if result.get("status") == "completed":
        try:
            visits = float(result.get("monthly_visits"))
        except (TypeError, ValueError):
            visits = None

    if visits is None:
        traffic_status = "pending"
    elif visits > TRAFFIC_THRESHOLD:
        traffic_status = "qualified"
    else:
        traffic_status = "below_threshold"

    # Persist successful traffic results across all duplicate rows.
    # On an API error, leave the current pending state untouched.
    if visits is not None:
        with get_db() as connection:
            connection.execute(
                """
                UPDATE campaign_records
                SET monthly_visits = ?,
                    traffic_status = ?
                WHERE campaign_id = ?
                  AND company_id = ?
                """,
                (visits, traffic_status, campaign_id, company_id),
            )

    findings = dict(result)
    findings.update({
        "traffic_status": "completed" if visits is not None else "unavailable",
        "research_status": "completed" if visits is not None else "unavailable",
        "eligibility_status": traffic_status,
        "threshold": TRAFFIC_THRESHOLD,
        "qualification_rule": "monthly_visits > 100000",
        "campaign_id": campaign_id,
    })

    add_research_record(
        company_id,
        "traffic_analysis",
        "TabAPI",
        findings,
        source_url=website,
    )

    return {
        "company_id": company_id,
        "company": company_name,
        "domain": domain,
        "monthly_visits": visits,
        "traffic_status": traffic_status,
        "credits_charged": result.get("credits_charged"),
        "reporting_month": result.get("reporting_month"),
        "global_rank": result.get("global_rank"),
        "country_rank": result.get("country_rank"),
        "error": result.get("error"),
        "requests_made": 1,
    }


def run_campaign_traffic_validation(campaign_id, months=3, batch_size=1):
    """
    Temporary compatibility wrapper for the old dashboard.

    It deliberately processes no more than ONE company per click, even if
    an old caller passes batch_size=10. This prevents accidental multi-credit
    usage while the dashboard is being migrated to the company selector.
    """
    candidates = get_campaign_traffic_candidates(campaign_id)

    if not candidates:
        return {
            "processed_this_batch": 0,
            "batch_size": 1,
            "remaining": 0,
            "results": [],
        }

    selected = candidates[0]

    try:
        result = run_single_company_traffic_validation(
            campaign_id,
            selected["company_id"],
            months=months,
        )
    except Exception as error:
        result = {
            "company_id": selected["company_id"],
            "company": selected["company_name"],
            "domain": selected["domain"],
            "monthly_visits": None,
            "traffic_status": "pending",
            "error": f"{type(error).__name__}: {error}",
            "requests_made": 0,
        }

    remaining = get_campaign_traffic_candidates(campaign_id)

    return {
        "processed_this_batch": 1,
        "batch_size": 1,
        "remaining": len(remaining),
        "results": [result],
    }


def score_campaign_leads(campaign_id):
    """Score every unique traffic-qualified company in a campaign."""
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT company_id
            FROM campaign_records
            WHERE campaign_id = ?
              AND company_id IS NOT NULL
            """,
            (campaign_id,),
        ).fetchall()

    results = []

    from database.campaign_research_queue import get_campaign_research_queue

    queue = {
        item["company_id"]: item
        for item in get_campaign_research_queue(campaign_id)
    }

    for row in rows:
        company_id = row["company_id"]

        try:
            entry = queue.get(company_id, {})

            if entry.get("traffic_status") != "qualified":
                results.append({
                    "company_id": company_id,
                    "qualification_status": "not_scored",
                    "error": "Traffic is not qualified.",
                })
                continue

            history = get_company_research_history(company_id)
            has_website_research = any(
                item.get("research_type") == "website_research"
                for item in history
            )

            if not has_website_research:
                run_company_research(
                    company_id=company_id,
                    mode="live",
                    monthly_visits_override=entry.get("monthly_visits"),
                    skip_traffic_api=True,
                )

            result = qualify_company(company_id, campaign_id=campaign_id)
            results.append(result)

        except Exception as error:
            results.append({
                "company_id": company_id,
                "qualification_status": "not_scored",
                "error": str(error),
            })

    return results


def get_campaign_intelligence(campaign_id):
    """Build a unified, current campaign dataframe from saved company and traffic records."""
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT
                cr.source_row_number,
                cr.source_brand_name AS company_name,
                COALESCE(c.website_url, cr.website) AS website,
                cr.monthly_visits,
                cr.traffic_status,
                c.qualification_score AS lead_score,
                c.qualification_category AS lead_category,
                c.data_completeness,
                c.id AS company_id
            FROM campaign_records cr
            JOIN companies c ON c.id = cr.company_id
            WHERE cr.campaign_id = ?
            ORDER BY cr.source_row_number
            """,
            (campaign_id,),
        ).fetchall()

    return pd.DataFrame([dict(row) for row in rows])


def build_campaign_report(campaign_id):
    """Create a multi-sheet Excel report from saved campaign intelligence."""
    data = get_campaign_intelligence(campaign_id)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name="Campaign Overview", index=False)

        if not data.empty:
            data.sort_values(
                "lead_score",
                ascending=False,
                na_position="last",
            ).to_excel(
                writer,
                sheet_name="Lead Prioritisation",
                index=False,
            )

            data[
                ["company_name", "website", "monthly_visits", "traffic_status"]
            ].to_excel(
                writer,
                sheet_name="Website Intelligence",
                index=False,
            )

        with get_db() as connection:
            contacts = connection.execute(
                """
                SELECT
                    c.company_name,
                    cc.contact_name,
                    cc.designation,
                    cc.email,
                    cc.phone,
                    cc.linkedin_url,
                    cc.contact_source,
                    cc.enrichment_status
                FROM company_contacts cc
                JOIN companies c ON c.id = cc.company_id
                JOIN campaign_records cr ON cr.company_id = c.id
                WHERE cr.campaign_id = ?
                GROUP BY cc.id
                ORDER BY c.company_name
                """,
                (campaign_id,),
            ).fetchall()

        pd.DataFrame([dict(row) for row in contacts]).to_excel(
            writer,
            sheet_name="Contact Intelligence",
            index=False,
        )

    output.seek(0)
    return output.getvalue()


def reset_campaign_traffic_to_pending(campaign_id):
    """Clear campaign traffic results so they can be individually revalidated."""
    with get_db() as connection:
        cursor = connection.execute(
            """
            UPDATE campaign_records
            SET monthly_visits = NULL,
                traffic_status = 'pending'
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        )
        return cursor.rowcount
