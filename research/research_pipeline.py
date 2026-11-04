
from database.company_repository import (
    get_company_by_id,
    mark_company_researched,
    update_company
)

from database.research_repository import (
    add_research_record
)

from research.website_research import research_company
from research.funding_research import collect_research


def run_company_research(company_id):
    """Research a company and save findings in SQLite."""

    company = get_company_by_id(company_id)

    if not company:
        raise ValueError(
            f"Company ID {company_id} not found."
        )

    company_name = company["company_name"]
    website_url = company["website_url"]

    print("\nQUIKLEE COMPANY RESEARCH")
    print("=" * 55)
    print("Company:", company_name)
    print("Website:", website_url)

    research_success = False
    research_errors = []

    # STEP 1: Website research
    print("\n[1/2] Researching official website...")

    website_result = research_company(website_url)

    if website_result.get("research_status") == "completed":

        add_research_record(
            company_id=company_id,
            research_type="website_research",
            source="Official Website",
            source_url=website_url,
            findings=website_result,
            confidence="unverified"
        )

        research_success = True

        print("Website research saved successfully.")

    else:
        research_errors.append("Website research failed")
        print("Website research could not be completed.")

    # STEP 2: Funding and growth research
    print("\n[2/2] Researching funding and growth...")

    try:

        funding_result = collect_research(company_name)

        add_research_record(
            company_id=company_id,
            research_type="funding_and_growth",
            source="Brave Search",
            findings=funding_result,
            confidence="unverified"
        )

        research_success = True

        print("Funding research saved successfully.")

    except (ValueError, RuntimeError) as error:

        research_errors.append(str(error))

        print("Funding research unavailable:", error)

    # STEP 3: Update company status
    if research_success:

        status = (
            "completed"
            if not research_errors
            else "partial"
        )

        update_company(
            company_id,
            {
                "research_status": status
            }
        )

    else:

        update_company(
            company_id,
            {
                "research_status": "failed"
            }
        )

    return {
        "company_id": company_id,
        "company_name": company_name,
        "research_status": (
            "completed" if research_success and not research_errors
            else "partial" if research_success
            else "failed"
        ),
        "errors": research_errors
    }


if __name__ == "__main__":

    print("\nAVAILABLE COMPANIES")
    print("=" * 45)

    from database.company_repository import get_all_companies

    companies = get_all_companies()

    if not companies:
        print("No companies found in the database.")

    else:

        for company in companies:
            print(
                f"ID: {company['id']} | "
                f"Name: {company['company_name']} | "
                f"Status: {company['research_status']}"
            )

        try:

            company_id = int(
                input("\nEnter company ID to research: ")
            )

            result = run_company_research(company_id)

            print("\nRESEARCH SUMMARY")
            print("=" * 45)

            for key, value in result.items():
                print(f"{key}: {value}")

        except (ValueError, RuntimeError) as error:
            print("\nResearch error:", error)
