"""Campaign-level research orchestration with an explicit external-call gate.

Dry-run is the default. No research or qualification writes occur in dry-run mode.
Execution requires both execute=True and confirm_external_calls=True.

Campaign-provided traffic figures are reused by default. TabAPI is not called
again unless refresh_traffic_api=True is explicitly supplied.
"""

from database.campaign_research_queue import get_campaign_research_queue
from research.research_pipeline import run_company_research
from qualification.qualification_pipeline import qualify_company


def build_campaign_research_plan(campaign_id):
    """Return a read-only plan for a campaign; does not call external APIs."""

    queue = get_campaign_research_queue(campaign_id)
    plan = []

    for company in queue:
        traffic_status = company.get("traffic_status")
        research_status = company.get("research_status")
        monthly_visits = company.get("monthly_visits")

        if traffic_status != "qualified":
            action = "blocked_by_traffic_eligibility"
        elif research_status == "completed":
            action = "skip_already_completed"
        elif research_status in {"partially_researched", "research_failed"}:
            action = "manual_review_before_retry"
        elif research_status == "research_in_progress":
            action = "skip_in_progress"
        elif research_status == "research_required":
            action = "ready_for_research"
        else:
            action = "manual_review"

        plan.append({
            "company_id": company["company_id"],
            "company_name": company["company_name"],
            "monthly_visits": monthly_visits,
            "traffic_status": traffic_status,
            "research_status": research_status,
            "action": action,
            "traffic_reuse_available": monthly_visits is not None,
        })

    return {
        "campaign_id": campaign_id,
        "mode": "dry_run",
        "external_calls_made": False,
        "companies": plan,
        "summary": {
            "total_companies": len(plan),
            "ready_for_research": sum(
                item["action"] == "ready_for_research" for item in plan
            ),
            "already_completed": sum(
                item["action"] == "skip_already_completed" for item in plan
            ),
            "blocked_by_traffic": sum(
                item["action"] == "blocked_by_traffic_eligibility"
                for item in plan
            ),
            "manual_review": sum(
                item["action"] in {
                    "manual_review",
                    "manual_review_before_retry",
                }
                for item in plan
            ),
            "in_progress": sum(
                item["action"] == "skip_in_progress" for item in plan
            ),
        },
    }


def run_campaign_research(
    campaign_id,
    *,
    execute=False,
    confirm_external_calls=False,
    refresh_traffic_api=False,
):
    """Preview or execute research for eligible, not-yet-researched companies.

    Execution requires BOTH execute=True and confirm_external_calls=True.

    By default, monthly visitor figures already attached to campaign records
    are passed to the research pipeline. This avoids an unnecessary TabAPI
    request. If no campaign visitor figure is available, the pipeline is told
    to skip TabAPI rather than making a paid lookup.

    Set refresh_traffic_api=True only when a fresh TabAPI lookup is intended
    and its possible credit cost has been explicitly approved.

    Partially researched and failed companies are not retried automatically.
    """

    if refresh_traffic_api and not (
        execute and confirm_external_calls
    ):
        raise PermissionError(
            "A TabAPI refresh requires explicit live execution approval. "
            "Set execute=True and confirm_external_calls=True only after "
            "approving possible TabAPI charges."
        )

    plan = build_campaign_research_plan(campaign_id)

    if not execute:
        return plan

    if not confirm_external_calls:
        raise PermissionError(
            "External research was not started. Set confirm_external_calls=True "
            "only after approving website requests and any explicitly enabled "
            "API usage."
        )

    results = []

    for item in plan["companies"]:
        if item["action"] != "ready_for_research":
            continue

        company_id = item["company_id"]
        campaign_visits = item.get("monthly_visits")

        company_result = {
            "company_id": company_id,
            "company_name": item["company_name"],
            "campaign_monthly_visits": campaign_visits,
            "traffic_reuse": (
                "campaign_dataset"
                if campaign_visits is not None
                else "no_campaign_value"
            ),
        }

        try:
            research_result = run_company_research(
                company_id=company_id,
                mode="live",
                monthly_visits_override=(
                    campaign_visits if campaign_visits is not None else None
                ),
                skip_traffic_api=not refresh_traffic_api,
            )

            company_result["research"] = research_result
            company_result["research_execution"] = "finished"

            try:
                qualification_result = qualify_company(
                    company_id=company_id,
                    campaign_id=campaign_id,
                )
                company_result["qualification"] = qualification_result
                company_result["qualification_execution"] = "scored"

            except ValueError as error:
                # Insufficient evidence is a valid outcome; do not invent a score.
                company_result["qualification_execution"] = "not_scored"
                company_result["qualification_message"] = str(error)

        except Exception as error:
            company_result["research_execution"] = "error"
            company_result["error"] = (
                f"{type(error).__name__}: {error}"
            )

        results.append(company_result)

    return {
        "campaign_id": campaign_id,
        "mode": "live_execution",
        "external_calls_made": bool(results),
        "companies_considered": plan["summary"]["ready_for_research"],
        "companies_attempted": len(results),
        "tabapi_refresh_enabled": refresh_traffic_api,
        "results": results,
        "note": (
            "Only companies marked ready_for_research were submitted. "
            "Campaign traffic was reused where available. TabAPI refresh was "
            "disabled unless explicitly requested. Partially researched and "
            "failed companies require manual review."
        ),
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description=(
            "Preview or explicitly execute a Quiklee campaign research plan."
        )
    )
    parser.add_argument("campaign_id", type=int)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute research instead of showing a dry-run plan.",
    )
    parser.add_argument(
        "--confirm-external-calls",
        action="store_true",
        help="Approve website requests and any explicitly enabled API usage.",
    )
    parser.add_argument(
        "--refresh-traffic-api",
        action="store_true",
        help="Explicitly request a fresh TabAPI traffic lookup (may cost credits).",
    )
    args = parser.parse_args()

    output = run_campaign_research(
        campaign_id=args.campaign_id,
        execute=args.execute,
        confirm_external_calls=args.confirm_external_calls,
        refresh_traffic_api=args.refresh_traffic_api,
    )
    print(json.dumps(output, indent=2, default=str))
