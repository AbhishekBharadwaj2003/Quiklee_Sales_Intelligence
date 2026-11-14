
from discovery.source_discovery import generate_search_queries
from discovery.brave_search import BraveSearchClient
from discovery.company_extractor import extract_company_candidates
from discovery.company_validator import validate_company
from discovery.deduplication import deduplicate_candidates
from discovery.demo_discovery import run_demo_discovery

from database.company_repository import (
    add_company,
    get_all_companies,
    update_company
)


def run_discovery(
    categories,
    queries_per_category=2,
    results_per_query=10,
    max_validations=20,
    mode="live"
):
    """
    Run company discovery.

    Demo Mode:
        Uses the local demo CSV without calling Brave Search.

    Live Mode:
        Uses Brave Search to discover new companies.
    """

    mode = mode.lower().strip()

    if mode not in {"demo", "live"}:
        raise ValueError("Mode must be either 'demo' or 'live'.")

    print("\nQUIKLEE DISCOVERY ENGINE")
    print("=" * 55)
    print(f"Discovery mode: {mode.upper()}")

    # DEMO MODE
    if mode == "demo":

        print("\nUsing local demo dataset.")
        print("Brave Search will not be called.")

        return run_demo_discovery(
            max_validations=max_validations
        )

    # LIVE MODE
    print("\nStarting live company discovery...")

    # STEP 1: Load existing companies
    existing_records = get_all_companies()

    print(f"Existing database records: {len(existing_records)}")

    # STEP 2: Initialize Brave Search
    client = BraveSearchClient()
    all_candidates = []

    # STEP 3: Discover companies
    for category in categories:

        print(f"\nSearching category: {category}")

        queries = generate_search_queries(category)

        for query in queries[:queries_per_category]:

            print(f"\nQuery: {query}")

            results = client.search(
                query=query,
                count=results_per_query
            )

            candidates = extract_company_candidates(
                search_results=results,
                category=category,
                query=query
            )

            all_candidates.extend(candidates)

    # STEP 4: Deduplicate
    unique, duplicates = deduplicate_candidates(
        all_candidates,
        existing_records
    )

    print("\nDISCOVERY SUMMARY")
    print("-" * 55)
    print(f"Candidates found: {len(all_candidates)}")
    print(f"New unique companies: {len(unique)}")
    print(f"Duplicates skipped: {len(duplicates)}")

    # STEP 5: Save new companies
    saved_records = []

    for candidate in unique:

        record = {
            **candidate,
            "validation_status": "pending"
        }

        result = add_company(record)

        if result["success"]:

            saved_records.append({
                "company_id": result["company_id"],
                "candidate": candidate
            })

    print(f"\nNew companies saved: {len(saved_records)}")

    # STEP 6: Validate saved companies
    validated_companies = []

    for record in saved_records[:max_validations]:

        company_id = record["company_id"]
        candidate = record["candidate"]

        print(
            f"\nValidating: "
            f"{candidate['company_name_candidate']}"
        )

        try:

            result = validate_company(candidate)

            validation_status = result["validation_status"]

            update_company(
                company_id,
                {
                    "validation_status": validation_status,
                    "description": result.get(
                        "website_description",
                        candidate.get("description", "")
                    )
                }
            )

            validated_companies.append({
                "company_id": company_id,
                "company_name": candidate["company_name_candidate"],
                "website_url": candidate["website_url"],
                "validation_status": validation_status
            })

            print(f"Status: {validation_status}")

        except Exception as error:

            update_company(
                company_id,
                {
                    "validation_status": "unreachable"
                }
            )

            print(f"Validation failed: {error}")

    pending_validation = max(
        0,
        len(saved_records) - len(validated_companies)
    )

    print("\nLIVE DISCOVERY SUMMARY")
    print("=" * 55)
    print("Candidates found:", len(all_candidates))
    print("Unique candidates:", len(unique))
    print("New companies saved:", len(saved_records))
    print("Companies validated:", len(validated_companies))
    print("Pending validation:", pending_validation)

    return {
        "total_candidates": len(all_candidates),
        "unique_candidates": len(unique),
        "duplicates": duplicates,
        "saved_records": len(saved_records),
        "validated_companies": validated_companies,
        "pending_validation": pending_validation
    }


if __name__ == "__main__":

    categories = [
        "beauty and personal care",
        "fashion and apparel"
    ]

    try:

        results = run_discovery(
            categories=categories,
            queries_per_category=2,
            results_per_query=5,
            max_validations=5,
            mode="demo"
        )

        print("\nFINAL PIPELINE SUMMARY")
        print("=" * 55)

        for key, value in results.items():

            if key == "duplicates":
                value = len(value)

            print(f"{key}: {value}")

    except (ValueError, RuntimeError) as error:
        print(f"\nPipeline error: {error}")
