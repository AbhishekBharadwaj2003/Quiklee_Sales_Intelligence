
from discovery.source_discovery import generate_search_queries
from discovery.brave_search import BraveSearchClient
from discovery.company_extractor import extract_company_candidates
from discovery.company_validator import validate_company
from discovery.deduplication import deduplicate_candidates

from database.company_repository import (
    add_company,
    get_all_companies,
    update_company
)


def run_discovery(
    categories,
    queries_per_category=2,
    results_per_query=10,
    max_validations=20
):
    """Run discovery, deduplication, validation and database storage."""

    print("\nQUIKLEE DISCOVERY ENGINE")
    print("=" * 55)

    # STEP 1: Load previously stored companies
    existing_records = get_all_companies()

    print(f"Existing database records: {len(existing_records)}")

    client = BraveSearchClient()
    all_candidates = []

    # STEP 2: Discover companies
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

    # STEP 3: Deduplicate against existing database records
    unique, duplicates = deduplicate_candidates(
        all_candidates,
        existing_records
    )

    print("\nDISCOVERY SUMMARY")
    print("-" * 55)
    print(f"Candidates found: {len(all_candidates)}")
    print(f"New unique companies: {len(unique)}")
    print(f"Duplicates skipped: {len(duplicates)}")

    # STEP 4: Save all new candidates in SQLite
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

    # STEP 5: Validate a limited number of saved companies
    validated_companies = []

    for record in saved_records[:max_validations]:

        company_id = record["company_id"]
        candidate = record["candidate"]

        print(
            f"\nValidating: "
            f"{candidate['company_name_candidate']}"
        )

        result = validate_company(candidate)

        update_company(
            company_id,
            {
                "validation_status": result["validation_status"],
                "description": result.get("website_description", "")
            }
        )

        validated_companies.append({
            "company_id": company_id,
            **result
        })

        print(f"Status: {result['validation_status']}")

    return {
        "total_candidates": len(all_candidates),
        "unique_candidates": len(unique),
        "duplicates": duplicates,
        "saved_records": len(saved_records),
        "validated_companies": validated_companies,
        "pending_validation": max(
            0,
            len(saved_records) - len(validated_companies)
        )
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
            max_validations=5
        )

        print("\nFINAL PIPELINE SUMMARY")
        print("=" * 55)

        for key, value in results.items():
            print(f"{key}: {value if key != 'duplicates' else len(value)}")

    except (ValueError, RuntimeError) as error:
        print(f"\nPipeline error: {error}")
