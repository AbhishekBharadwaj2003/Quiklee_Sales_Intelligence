
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

import tldextract


domain_extractor = tldextract.TLDExtract(
    suffix_list_urls=()
)

# Common legal suffixes and generic terms
LEGAL_SUFFIXES = {
    "private", "limited", "ltd", "pvt",
    "llp", "inc", "incorporated",
    "company", "co", "corporation", "corp"
}


def normalize_domain(url: str) -> str:
    """Convert different URLs of the same website to one domain."""

    try:
        extracted = domain_extractor(url)

        if not extracted.domain or not extracted.suffix:
            return ""

        return f"{extracted.domain}.{extracted.suffix}".lower()

    except Exception:
        return ""


def normalize_company_name(name: str) -> str:
    """Normalize company names for duplicate comparison."""

    name = name.lower().strip()

    name = re.sub(r"[^a-z0-9\s]", " ", name)

    words = name.split()

    words = [
        word for word in words
        if word not in LEGAL_SUFFIXES
    ]

    return " ".join(words)


def calculate_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two company names."""

    normalized1 = normalize_company_name(name1)
    normalized2 = normalize_company_name(name2)

    if not normalized1 or not normalized2:
        return 0.0

    return SequenceMatcher(
        None,
        normalized1,
        normalized2
    ).ratio()


def find_duplicate(
    candidate: dict,
    existing_records: list,
    similarity_threshold: float = 0.92
):
    """Check whether a company already exists."""

    candidate_domain = normalize_domain(
        candidate.get("website_url", "")
    )

    candidate_name = candidate.get(
        "company_name_candidate", ""
    )

    for existing in existing_records:

        existing_domain = normalize_domain(
            existing.get("website_url", "")
        )

        existing_name = existing.get(
            "company_name_candidate",
            existing.get("company_name", "")
        )

        # Exact domain match
        if (
            candidate_domain
            and existing_domain
            and candidate_domain == existing_domain
        ):
            return {
                "is_duplicate": True,
                "matched_company": existing_name,
                "reason": "Domain match",
                "similarity": 1.0
            }

        # Normalized company name match
        similarity = calculate_similarity(
            candidate_name,
            existing_name
        )

        if similarity >= similarity_threshold:
            return {
                "is_duplicate": True,
                "matched_company": existing_name,
                "reason": "Company name similarity",
                "similarity": round(similarity, 3)
            }

    return {
        "is_duplicate": False,
        "matched_company": None,
        "reason": "New company",
        "similarity": 0.0
    }


def deduplicate_candidates(
    candidates: list,
    existing_records: list
):
    """Remove duplicates from existing records and current batch."""

    unique_companies = []
    duplicate_companies = []

    # Copy existing records to avoid modifying the original list
    known_records = list(existing_records)

    for candidate in candidates:

        result = find_duplicate(
            candidate,
            known_records
        )

        if result["is_duplicate"]:

            duplicate_companies.append({
                **candidate,
                "duplicate_reason": result["reason"],
                "matched_company": result["matched_company"]
            })

        else:

            unique_companies.append(candidate)

            # Prevent duplicates within the same discovery batch
            known_records.append(candidate)

    return unique_companies, duplicate_companies


if __name__ == "__main__":

    existing_records = [
        {
            "company_name": "Mamaearth",
            "website_url": "https://www.mamaearth.in/"
        },
        {
            "company_name": "Boat",
            "website_url": "https://www.boat-lifestyle.com/"
        }
    ]

    discovered_companies = [
        {
            "company_name_candidate": "Mamaearth",
            "website_url": "https://mamaearth.in/about"
        },
        {
            "company_name_candidate": "boAt Lifestyle",
            "website_url": "https://www.boat-lifestyle.com/"
        },
        {
            "company_name_candidate": "New Fashion Brand",
            "website_url": "https://www.newfashionbrand.in/"
        },
        {
            "company_name_candidate": "New Beauty Brand",
            "website_url": "https://www.newbeautybrand.in/"
        },
        {
            "company_name_candidate": "New Fashion Brand",
            "website_url": "https://newfashionbrand.in/"
        }
    ]

    unique, duplicates = deduplicate_candidates(
        discovered_companies,
        existing_records
    )

    print("\nQUIKLEE DEDUPLICATION ENGINE")
    print("=" * 50)

    print(f"Discovered companies: {len(discovered_companies)}")
    print(f"Unique companies: {len(unique)}")
    print(f"Duplicates: {len(duplicates)}")

    print("\nUNIQUE COMPANIES")

    for company in unique:
        print("-", company["company_name_candidate"])

    print("\nDUPLICATE COMPANIES")

    for company in duplicates:
        print(
            f"- {company['company_name_candidate']} | "
            f"Reason: {company['duplicate_reason']} | "
            f"Matched: {company['matched_company']}"
        )
