
from database.db import get_db


TRAFFIC_THRESHOLD = 100000

SUCCESS_STATUSES = {"completed", "partial", "success", "available"}


def _parse_findings(value):
    """Safely parse research findings stored as JSON."""

    import json

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    return {}


def _research_component_status(research_type, findings):
    """Determine whether an individual research component succeeded."""

    status = str(
        findings.get("research_status")
        or findings.get("traffic_status")
        or ""
    ).strip().lower()

    if status in {"failed", "unavailable", "error"}:
        return "failed"

    if research_type == "website_research":
        if status in SUCCESS_STATUSES:
            return "completed"

    elif research_type == "traffic_analysis":
        visits = findings.get("monthly_visits")

        try:
            if visits is not None and float(visits) > 0:
                return "completed"
        except (TypeError, ValueError):
            pass

        if status in SUCCESS_STATUSES:
            return "completed"

    elif research_type == "business_metrics":
        metrics_status = str(
            findings.get("overall_data_type") or ""
        ).strip().lower()

        if metrics_status not in {"", "unavailable", "failed", "error"}:
            return "completed"

    elif research_type == "funding_and_growth":
        if status == "completed":
            return "completed"

    if status == "partial":
        return "partial"

    return "failed"


def _summarize_research(records, company_status):
    """
    Summarize the latest research result for each component.

    Core components:
    - Website research
    - Traffic analysis
    - Business metrics

    Funding and growth research is tracked separately.
    """

    latest = {}

    for record in records:
        research_type = record["research_type"]

        if research_type not in latest:
            latest[research_type] = _parse_findings(
                record["findings"]
            )

    components = {
        research_type: _research_component_status(
            research_type,
            findings
        )
        for research_type, findings in latest.items()
    }

    core_types = (
        "website_research",
        "traffic_analysis",
        "business_metrics",
    )

    completed_core = sum(
        components.get(research_type) == "completed"
        for research_type in core_types
    )

    has_partial = any(
        status == "partial"
        for status in components.values()
    )

    if all(
        components.get(research_type) == "completed"
        for research_type in core_types
    ):
        status = "completed"

    elif completed_core > 0 or has_partial:
        status = "partially_researched"

    elif str(company_status or "").lower() == "in_progress":
        status = "research_in_progress"

    elif records:
        status = "research_failed"

    else:
        status = "research_required"

    return {
        "research_status": status,
        "research_components": components,
        "completed_core_components": completed_core,
        "required_core_components": len(core_types),
        "existing_research_records": len(records),
    }


def get_campaign_research_queue(campaign_id):
    """
    Build a research queue with one entry per unique company.

    Traffic eligibility:
    - >= 100,000: eligible for research
    - < 100,000: excluded
    - Missing or conflicting traffic: manual review

    This function performs database reads only.
    No external APIs are called.
    """

    with get_db() as connection:

        records = connection.execute(
            """
            SELECT
                cr.company_id,
                cr.source_brand_name,
                cr.monthly_visits,
                cr.traffic_status,
                c.company_name,
                c.website_url,
                c.research_status,
                c.qualification_score,
                c.qualification_category,
                c.data_completeness
            FROM campaign_records cr
            JOIN companies c
                ON c.id = cr.company_id
            WHERE cr.campaign_id = ?
            ORDER BY cr.source_row_number
            """,
            (campaign_id,),
        ).fetchall()

        research_records = connection.execute(
            """
            SELECT
                rh.company_id,
                rh.research_type,
                rh.findings,
                rh.researched_at
            FROM research_history rh
            JOIN campaign_records cr
                ON cr.company_id = rh.company_id
            WHERE cr.campaign_id = ?
            ORDER BY rh.researched_at DESC
            """,
            (campaign_id,),
        ).fetchall()

    grouped = {}

    for record in records:

        item = dict(record)
        company_id = item["company_id"]

        if company_id not in grouped:

            grouped[company_id] = {
                "company_id": company_id,
                "company_name": item["company_name"],
                "website": item["website_url"],
                "traffic_values": set(),
                "traffic_statuses": set(),
                "source_rows": 0,
                "company_research_status": item["research_status"],
                "lead_score": item["qualification_score"],
                "lead_category": item["qualification_category"],
                "data_completeness": item["data_completeness"],
            }

        group = grouped[company_id]
        group["source_rows"] += 1

        if item["monthly_visits"] is not None:
            try:
                group["traffic_values"].add(
                    float(item["monthly_visits"])
                )
            except (TypeError, ValueError):
                pass

        group["traffic_statuses"].add(
            item["traffic_status"]
        )

    history_by_company = {}

    for record in research_records:

        item = dict(record)

        history_by_company.setdefault(
            item["company_id"],
            []
        ).append(item)

    queue = []

    for company_id, group in grouped.items():

        values = group["traffic_values"]
        statuses = group["traffic_statuses"]

        if len(values) > 1:
            traffic_status = "manual_review"
            monthly_visits = None

        elif not values:
            traffic_status = "pending"
            monthly_visits = None

        else:
            monthly_visits = next(iter(values))

            if monthly_visits >= TRAFFIC_THRESHOLD:
                traffic_status = "qualified"
            else:
                traffic_status = "below_threshold"

        if (
            len(statuses) > 1
            and traffic_status != "manual_review"
        ):
            traffic_status = "manual_review"

        research_history = history_by_company.get(
            company_id,
            []
        )

        research_summary = _summarize_research(
            research_history,
            group["company_research_status"]
        )

        if traffic_status == "qualified":
            research_status = research_summary["research_status"]

        elif traffic_status == "below_threshold":
            research_status = "excluded"

        else:
            research_status = "traffic_verification_required"

        queue.append({
            "company_id": company_id,
            "company_name": group["company_name"],
            "website": group["website"],
            "monthly_visits": monthly_visits,
            "traffic_status": traffic_status,
            "research_status": research_status,
            "existing_research_records": (
                research_summary["existing_research_records"]
            ),
            "research_components": (
                research_summary["research_components"]
            ),
            "completed_core_components": (
                research_summary["completed_core_components"]
            ),
            "required_core_components": (
                research_summary["required_core_components"]
            ),
            "source_rows": group["source_rows"],
            "lead_score": group["lead_score"],
            "lead_category": group["lead_category"],
            "data_completeness": group["data_completeness"],
        })

    queue.sort(
        key=lambda item: (
            item["traffic_status"] != "qualified",
            -(item["monthly_visits"] or 0),
            item["company_name"].lower(),
        )
    )

    return queue


def get_research_queue_summary(queue):
    """Calculate campaign research queue statistics."""

    return {
        "unique_companies": len(queue),

        "research_eligible": sum(
            item["traffic_status"] == "qualified"
            for item in queue
        ),

        "below_threshold": sum(
            item["traffic_status"] == "below_threshold"
            for item in queue
        ),

        "pending_verification": sum(
            item["traffic_status"] == "pending"
            for item in queue
        ),

        "manual_review": sum(
            item["traffic_status"] == "manual_review"
            for item in queue
        ),

        "research_required": sum(
            item["research_status"] == "research_required"
            for item in queue
        ),

        "research_in_progress": sum(
            item["research_status"] == "research_in_progress"
            for item in queue
        ),

        "partially_researched": sum(
            item["research_status"] == "partially_researched"
            for item in queue
        ),

        "research_failed": sum(
            item["research_status"] == "research_failed"
            for item in queue
        ),

        "already_researched": sum(
            item["research_status"] == "completed"
            for item in queue
        ),
    }
