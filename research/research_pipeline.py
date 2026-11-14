from datetime import date, timedelta
from urllib.parse import urlparse

from database.company_repository import get_company_by_id, update_company
from database.research_repository import add_research_record
from research.website_research import research_company as research_website
from research.traffic_analysis import analyse_traffic
from research.business_metrics import calculate_business_metrics


def get_last_three_completed_months():
    """Return the last three fully completed calendar months."""

    today = date.today()
    first_day_current_month = date(today.year, today.month, 1)
    last_day_previous_month = first_day_current_month - timedelta(days=1)

    start_month_index = today.year * 12 + today.month - 1 - 3
    start_year = start_month_index // 12
    start_month = start_month_index % 12 + 1

    return (
        f"{start_year}-{start_month:02d}",
        last_day_previous_month.strftime("%Y-%m"),
    )


def get_company_domain(company):
    """Extract a clean domain from the company record."""

    domain = company.get("domain")

    if domain:
        return domain.replace("www.", "").strip().lower()

    website_url = company.get("website_url") or ""
    parsed = urlparse(website_url if "://" in website_url else f"https://{website_url}")

    return parsed.netloc.replace("www.", "").strip().lower()


def _normalise_monthly_visits(value):
    """Return a positive numeric monthly-visit value, or None."""

    if value is None:
        return None

    try:
        visits = float(value)
    except (TypeError, ValueError):
        return None

    if visits <= 0:
        return None

    return int(visits) if visits.is_integer() else visits


def run_company_research(
    company_id,
    mode="live",
    *,
    monthly_visits_override=None,
    skip_traffic_api=False,
):
    """
    Research a company using its official website, TabAPI traffic data,
    and the existing business-metrics engine.

    This version deliberately does not call Brave Search, funding research,
    or a public-search fallback.

    Traffic handling:
    - If monthly_visits_override is supplied, save and reuse that value.
    - If skip_traffic_api=True, do not call TabAPI.
    - Otherwise, call TabAPI through analyse_traffic().

    Website research may still access the company's public website.
    TabAPI calls can incur usage/credit charges.
    """

    if mode not in ("demo", "live"):
        raise ValueError("Mode must be 'demo' or 'live'.")

    company = get_company_by_id(company_id)

    if not company:
        raise ValueError(f"Company ID {company_id} not found.")

    company_name = company["company_name"]
    website_url = company.get("website_url") or ""
    domain = get_company_domain(company)

    print("\nQUIKLEE COMPANY RESEARCH")
    print("=" * 55)
    print("Company:", company_name)
    print("Domain:", domain or "Unavailable")
    print("Mode:", mode.upper())

    research_errors = []

    website_status = "not_started"
    traffic_status = "not_started"
    business_metrics_status = "not_started"

    website_success = False
    traffic_result = {}

    # STEP 1: Official website research
    print("\n[1/3] Researching official website...")

    if not website_url:
        website_status = "unavailable"
        website_result = {
            "research_status": "unavailable",
            "error": "Company website is unavailable.",
        }
        research_errors.append("Company website is unavailable.")
    else:
        try:
            website_result = research_website(website_url) or {}
            website_status = str(
                website_result.get("research_status", "failed")
            ).lower()

            add_research_record(
                company_id=company_id,
                research_type="website_research",
                source="Official Website",
                source_url=website_url,
                findings=website_result,
                confidence="unverified",
            )

            website_success = website_status in {"completed", "partial"}

            if website_success:
                print(
                    "Website research saved. Quality:",
                    website_result.get("research_quality", "unknown"),
                )
            else:
                research_errors.append(
                    website_result.get(
                        "error",
                        "Official website research did not complete.",
                    )
                )

        except Exception as error:
            website_status = "failed"
            error_message = (
                f"Website research exception: {type(error).__name__}: {error}"
            )
            research_errors.append(error_message)
            website_result = {
                "research_status": "failed",
                "error": error_message,
            }
            print(error_message)

            try:
                add_research_record(
                    company_id=company_id,
                    research_type="website_research",
                    source="Official Website",
                    source_url=website_url or None,
                    findings=website_result,
                    confidence="unverified",
                )
            except Exception as save_error:
                print("Could not save website failure:", save_error)

    # STEP 2: Traffic research
    print("\n[2/3] Processing website traffic...")

    override_visits = _normalise_monthly_visits(monthly_visits_override)

    if override_visits is not None:
        traffic_result = {
            "domain": domain,
            "monthly_visits": override_visits,
            "traffic_status": "completed",
            "research_status": "completed",
            "status": "completed",
            "data_source": "Campaign Dataset",
            "error": None,
            "api_call_skipped": True,
        }
        traffic_status = "completed"

        add_research_record(
            company_id=company_id,
            research_type="traffic_analysis",
            source="Campaign Dataset",
            source_url=None,
            findings=traffic_result,
            confidence="unverified",
        )
        print("Using monthly visitors supplied by the campaign dataset.")
        print("Monthly visits:", override_visits)

    elif skip_traffic_api:
        traffic_status = "skipped"
        traffic_result = {
            "domain": domain,
            "monthly_visits": None,
            "traffic_status": "skipped",
            "research_status": "skipped",
            "status": "skipped",
            "data_source": "TabAPI",
            "error": "TabAPI lookup was explicitly skipped.",
        }
        print("TabAPI lookup skipped; no traffic API call was made.")

    elif not domain:
        traffic_status = "unavailable"
        traffic_result = {
            "domain": None,
            "monthly_visits": None,
            "traffic_status": "unavailable",
            "research_status": "unavailable",
            "status": "unavailable",
            "data_source": "TabAPI",
            "error": "Company domain is unavailable.",
        }
        research_errors.append("Traffic analysis skipped: domain unavailable.")

        add_research_record(
            company_id=company_id,
            research_type="traffic_analysis",
            source="TabAPI",
            findings=traffic_result,
            confidence="unverified",
        )

    else:
        try:
            start_date, end_date = get_last_three_completed_months()

            tabapi_result = analyse_traffic(
                domain=domain,
                start_date=start_date,
                end_date=end_date,
                months=3,
            ) or {}

            # traffic_analysis.py returns "status"; retain compatibility
            # with implementations that return "traffic_status".
            result_status = str(
                tabapi_result.get("traffic_status")
                or tabapi_result.get("status")
                or "unavailable"
            ).lower()

            visits = _normalise_monthly_visits(
                tabapi_result.get("monthly_visits")
            )

            if result_status == "completed" and visits is not None:
                traffic_status = "completed"
            else:
                traffic_status = "unavailable"

            traffic_result = {
                **tabapi_result,
                "domain": tabapi_result.get("domain", domain),
                "monthly_visits": visits,
                "traffic_status": traffic_status,
                "research_status": traffic_status,
                "status": traffic_status,
                "data_source": "TabAPI",
            }

            add_research_record(
                company_id=company_id,
                research_type="traffic_analysis",
                source="TabAPI",
                source_url=f"https://tabapi.com/",
                findings=traffic_result,
                confidence="unverified",
            )

            if traffic_status == "completed":
                print("TabAPI traffic research saved.")
                print("Monthly visits:", visits)
            else:
                error_message = traffic_result.get(
                    "error",
                    "TabAPI did not return a usable monthly-visits value.",
                )
                research_errors.append(str(error_message))
                print("Traffic analysis unavailable:", error_message)

        except Exception as error:
            traffic_status = "unavailable"
            error_message = (
                f"TabAPI traffic exception: {type(error).__name__}: {error}"
            )
            research_errors.append(error_message)

            traffic_result = {
                "domain": domain,
                "monthly_visits": None,
                "traffic_status": "unavailable",
                "research_status": "unavailable",
                "status": "unavailable",
                "data_source": "TabAPI",
                "error": error_message,
            }

            print(error_message)

            try:
                add_research_record(
                    company_id=company_id,
                    research_type="traffic_analysis",
                    source="TabAPI",
                    source_url="https://tabapi.com/",
                    findings=traffic_result,
                    confidence="unverified",
                )
            except Exception as save_error:
                print("Could not save traffic failure:", save_error)

    # STEP 3: Business metrics
    print("\n[3/3] Calculating business metrics...")

    try:
        monthly_visits = _normalise_monthly_visits(
            traffic_result.get("monthly_visits")
        )

        metrics_result = calculate_business_metrics(
            monthly_visits=monthly_visits,
            aov=None,
            cod_share=None,
        ) or {}

        business_metrics_status = metrics_result.get(
            "overall_data_type",
            "unavailable",
        )

        add_research_record(
            company_id=company_id,
            research_type="business_metrics",
            source="Quiklee Business Metrics Engine",
            findings=metrics_result,
            confidence=(
                "estimated" if monthly_visits is not None else "unavailable"
            ),
        )

        print("Business metrics status:", business_metrics_status)

    except Exception as error:
        business_metrics_status = "failed"
        error_message = (
            f"Business metrics exception: {type(error).__name__}: {error}"
        )
        research_errors.append(error_message)

        metrics_result = {
            "overall_data_type": "unavailable",
            "error": error_message,
        }

        print(error_message)

        try:
            add_research_record(
                company_id=company_id,
                research_type="business_metrics",
                source="Quiklee Business Metrics Engine",
                findings=metrics_result,
                confidence="unverified",
            )
        except Exception as save_error:
            print("Could not save business metrics failure:", save_error)

    # Calculate overall research status.
    core_statuses = [
        website_status,
        traffic_status,
        str(business_metrics_status).lower(),
    ]

    successful_components = sum(
        status in {"completed", "partial", "estimated"}
        for status in core_statuses
    )

    if all(
        status in {"completed", "estimated"}
        for status in core_statuses
    ):
        overall_status = "completed"
    elif successful_components > 0:
        overall_status = "partial"
    else:
        overall_status = "failed"

    update_company(
        company_id,
        {"research_status": overall_status},
    )

    return {
        "company_id": company_id,
        "company_name": company_name,
        "mode": mode,
        "website_status": website_status,
        "traffic_status": traffic_status,
        "traffic_source": traffic_result.get("data_source"),
        "monthly_visits": traffic_result.get("monthly_visits"),
        "business_metrics_status": business_metrics_status,
        "research_status": overall_status,
        "errors": research_errors,
    }


if __name__ == "__main__":
    from database.company_repository import get_all_companies

    companies = get_all_companies()

    if not companies:
        print("No companies found.")
        raise SystemExit

    for company in companies:
        print(
            f"ID: {company['id']} | "
            f"Name: {company['company_name']}"
        )

    try:
        company_id = int(input("\nEnter company ID: "))
        mode = input("Enter mode (demo/live): ").strip().lower()

        result = run_company_research(
            company_id=company_id,
            mode=mode,
        )

        print("\nRESEARCH SUMMARY")
        print("=" * 45)

        for key, value in result.items():
            print(f"{key}: {value}")

    except (ValueError, RuntimeError) as error:
        print("\nResearch error:", error)
