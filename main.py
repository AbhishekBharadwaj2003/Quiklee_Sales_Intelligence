from database.db import initialize_database
from discovery.discovery_scheduler import run_discovery

from research.research_pipeline import research_company
from qualification.qualification_pipeline import qualify_company

from config.settings import CATEGORIES


def run_pipeline():

    print("\nQUIKLEE SALES INTELLIGENCE")
    print("=" * 60)

    # STEP 1: Initialize database
    print("\n[1/4] Initializing database...")

    initialize_database()

    print("Database ready.")

    # STEP 2: Discover companies
    print("\n[2/4] Starting company discovery...")

    discovery_results = run_discovery(
        categories=CATEGORIES,
        queries_per_category=2,
        results_per_query=10,
        max_validations=20
    )

    print("\nDiscovery completed.")

    # STEP 3: Research validated companies
    print("\n[3/4] Starting company research...")

    researched_count = 0

    for company in discovery_results["validated_companies"]:

        if company["validation_status"] != "promising_candidate":
            continue

        company_id = company["company_id"]

        print(f"\nResearching company ID: {company_id}")

        try:

            result = research_company(company_id)

            print("Research status:", result["research_status"])

            researched_count += 1

        except Exception as error:

            print("Research failed:", error)

    # STEP 4: Pipeline summary
    print("\n[4/4] Pipeline execution summary")
    print("=" * 60)

    print(
        "Companies discovered:",
        discovery_results["total_candidates"]
    )

    print(
        "New companies saved:",
        discovery_results["saved_records"]
    )

    print(
        "Companies validated:",
        len(discovery_results["validated_companies"])
    )

    print(
        "Companies researched:",
        researched_count
    )

    print("\nPipeline execution completed.")


if __name__ == "__main__":

    try:
        run_pipeline()

    except Exception as error:
        print(f"\nPIPELINE ERROR: {error}")