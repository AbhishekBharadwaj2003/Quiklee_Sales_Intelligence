
import csv
from pathlib import Path

from discovery.company_extractor import extract_company_candidates
from discovery.deduplication import deduplicate_candidates
from discovery.company_validator import validate_company

from database.company_repository import (
    add_company,
    get_all_companies,
    get_company_by_domain,
    update_company
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_FILE = PROJECT_ROOT / "data" / "demo_companies.csv"


def load_demo_companies():

    if not DEMO_FILE.exists():
        raise FileNotFoundError(
            f"Demo dataset not found: {DEMO_FILE}"
        )

    candidates = []

    with open(
        DEMO_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        required_columns = {
            "company_name",
            "website_url",
            "category",
            "description",
            "headquarters"
        }

        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(
                "CSV is missing required columns."
            )

        for row in reader:

            candidates.append({
                "title": row["company_name"].strip(),
                "url": row["website_url"].strip(),
                "description": row["description"].strip(),
                "headquarters": row["headquarters"].strip(),
                "category": row["category"].strip()
            })

    return candidates


def run_demo_discovery(max_validations=20):

    print("\nQUIKLEE SALES INTELLIGENCE - DEMO MODE")
    print("=" * 55)

    # STEP 1: Load local CSV
    raw_companies = load_demo_companies()

    print(f"Sample records loaded: {len(raw_companies)}")

    # STEP 2: Extract candidates
    all_candidates = []

    for category in sorted({
        company["category"]
        for company in raw_companies
    }):

        category_records = [
            company for company in raw_companies
            if company["category"] == category
        ]

        extracted = extract_company_candidates(
            search_results=category_records,
            category=category,
            query="Local demo CSV",
            source="Demo CSV"
        )

        for candidate in extracted:

            original = next(
                company for company in category_records
                if company["url"] == candidate["website_url"]
            )

            candidate["headquarters"] = original["headquarters"]

            all_candidates.append(candidate)

    print(f"Candidates extracted: {len(all_candidates)}")

    # STEP 3: Deduplicate
    existing_records = get_all_companies()

    unique, duplicates = deduplicate_candidates(
        all_candidates,
        existing_records
    )

    print(f"New unique candidates: {len(unique)}")
    print(f"Duplicates skipped: {len(duplicates)}")

    # STEP 4: Save new companies
    saved_records = []

    for candidate in unique:

        result = add_company({
            **candidate,
            "validation_status": "pending"
        })

        if result["success"]:
            saved_records.append(result["company_id"])

    print(f"New records saved: {len(saved_records)}")

    # STEP 5: Resolve all CSV companies from database
    validated_companies = []
    validation_attempts = 0
    pending_validation = 0

    for candidate in all_candidates:

        company = get_company_by_domain(
            candidate["website_url"]
        )

        if not company:
            print(
                "Warning: Could not resolve company:",
                candidate["company_name_candidate"]
            )
            continue

        company_id = company["id"]
        validation_status = company.get(
            "validation_status",
            "pending"
        )

        # Validate pending records within the configured limit
        if (
            validation_status in {"pending", "unreachable"}
            and validation_attempts < max_validations
        ):

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
                            candidate["description"]
                        )
                    }
                )

                validation_attempts += 1

                print(
                    "Validation status:",
                    validation_status
                )

            except Exception as error:

                validation_status = "unreachable"

                update_company(
                    company_id,
                    {
                        "validation_status": validation_status
                    }
                )

                validation_attempts += 1

                print("Validation failed:", error)

        if validation_status == "pending":
            pending_validation += 1

        validated_companies.append({
            "company_id": company_id,
            "company_name": candidate["company_name_candidate"],
            "website_url": candidate["website_url"],
            "validation_status": validation_status
        })

    print("\nDEMO DISCOVERY SUMMARY")
    print("=" * 55)
    print("Companies loaded:", len(raw_companies))
    print("Candidates extracted:", len(all_candidates))
    print("New companies:", len(saved_records))
    print("Duplicates skipped:", len(duplicates))
    print("Companies available:", len(validated_companies))
    print("Validation attempts:", validation_attempts)

    return {
        "total_candidates": len(all_candidates),
        "unique_candidates": len(unique),
        "duplicates": duplicates,
        "saved_records": len(saved_records),
        "validated_companies": validated_companies,
        "pending_validation": pending_validation
    }


if __name__ == "__main__":

    try:

        summary = run_demo_discovery()

        print("\nFINAL DEMO SUMMARY")
        print("=" * 55)

        for key, value in summary.items():
            if key == "duplicates":
                value = len(value)

            print(f"{key}: {value}")

    except Exception as error:
        print(f"\nDEMO PIPELINE ERROR: {error}")
