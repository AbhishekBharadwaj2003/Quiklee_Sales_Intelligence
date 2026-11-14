
from database.db import initialize_database
from discovery.discovery_scheduler import run_discovery

from research.research_pipeline import run_company_research
from qualification.qualification_pipeline import qualify_company

from config.settings import CATEGORIES


def run_pipeline(mode="demo"):

    mode = mode.lower().strip()

    if mode not in {"demo", "live"}:
        raise ValueError("Mode must be either 'demo' or 'live'.")

    print("\nQUIKLEE SALES INTELLIGENCE")
    print("=" * 60)
    print(f"Execution Mode: {mode.upper()}")

    # STEP 1: Initialize database
    print("\n[1/5] Initializing database...")

    initialize_database()

    print("Database ready.")

    # STEP 2: Discover companies
    print("\n[2/5] Starting company discovery...")

    discovery_results = run_discovery(
        categories=CATEGORIES,
        queries_per_category=2,
        results_per_query=10,
        max_validations=20,
        mode=mode
    )

    print("\nDiscovery completed.")

    # STEP 3: Research validated companies
    print("\n[3/5] Starting company research...")

    researched_count = 0
    research_failed_count = 0
    research_company_ids = []

    for company in discovery_results["validated_companies"]:

        if company["validation_status"] != "promising_candidate":
            continue

        company_id = company["company_id"]

        print(f"\nResearching company: {company.get('company_name', company_id)}")

        try:

            result = run_company_research(
                company_id,
                mode=mode
            )

            research_status = result.get(
                "research_status",
                "unknown"
            )

            print("Research status:", research_status)

            if research_status == "failed":

                research_failed_count += 1
                print("Company research was unsuccessful.")
                continue

            researched_count += 1
            research_company_ids.append(company_id)

        except Exception as error:

            research_failed_count += 1
            print("Research failed:", error)

    # STEP 4: Automated lead qualification
    print("\n[4/5] Starting automated lead qualification...")

    qualified_count = 0
    qualification_failed_count = 0

    for company_id in research_company_ids:

        print(f"\nQualifying company ID: {company_id}")

        try:

            result = qualify_company(company_id)

            print("Company:", result["company_name"])
            print("Lead score:", result["lead_score"])
            print("Category:", result["qualification_category"])
            print("Qualification status:", result["qualification_status"])
            print("Data completeness:", result["data_completeness"], "%")

            qualified_count += 1

        except Exception as error:

            qualification_failed_count += 1

            print(
                f"Qualification failed for company ID "
                f"{company_id}: {error}"
            )

    # STEP 5: Pipeline summary
    print("\n[5/5] Pipeline execution summary")
    print("=" * 60)

    print("Execution mode:", mode.upper())

    print(
        "Companies discovered:",
        discovery_results["total_candidates"]
    )

    print(
        "New companies saved:",
        discovery_results["saved_records"]
    )

    print(
        "Companies available:",
        len(discovery_results["validated_companies"])
    )

    print("Companies researched:", researched_count)
    print("Research failures:", research_failed_count)
    print("Companies qualified:", qualified_count)
    print("Qualification failures:", qualification_failed_count)

    print("\nPipeline execution completed.")


if __name__ == "__main__":

    try:
        run_pipeline(mode="demo")

    except Exception as error:
        print(f"\nPIPELINE ERROR: {error}")
