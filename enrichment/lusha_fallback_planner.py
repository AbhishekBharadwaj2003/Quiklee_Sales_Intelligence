
from pathlib import Path
import re

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

HISTORY_FILE = (
    ROOT / "data" / "lusha_prospecting" / "search_history.csv"
)

CONTACTS_FILE = ROOT / "data" / "lusha_discovered_contacts.csv"

OUTPUT_FILE = ROOT / "data" / "lusha_fallback_search_queue.csv"


FALLBACK_TITLES = {
    "Operations Head": [
        "Operations Manager",
        "Business Operations Manager",
        "General Manager",
        "Head of Business Operations"
    ],
    "Growth Head": [
        "Growth Manager",
        "Business Growth Manager",
        "Marketing Director",
        "Head of Marketing"
    ],
    "Supply Chain Head": [
        "Supply Chain Manager",
        "Logistics Manager",
        "Procurement Manager",
        "Head of Logistics"
    ],
    "Marketplace / E-commerce": [
        "E Commerce Manager",
        "E Commerce Business Manager",
        "Marketplace Manager",
        "D2C Business Manager"
    ]
}


def normalize(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower().strip()
    )


def infer_role(contact):

    title = str(contact.get("job_title", "")).lower()
    source = str(contact.get("discovery_source", "")).lower()

    if "growth" in title:
        return "Growth Head"

    if "operation" in title:
        return "Operations Head"

    if "supply chain" in title:
        return "Supply Chain Head"

    if any(term in title for term in [
        "marketplace", "e-commerce", "e commerce", "d2c"
    ]):
        return "Marketplace / E-commerce"

    if "general manager" in title and "broader_title_test" in source:
        return "Operations Head"

    return None


def main():

    if not HISTORY_FILE.exists():
        raise FileNotFoundError(
            f"Search history not found: {HISTORY_FILE}"
        )

    history = pd.read_csv(
        HISTORY_FILE,
        dtype=str
    ).fillna("")

    required = [
        "search_id",
        "company_name",
        "company_domain",
        "role_category",
        "status",
        "contacts_returned"
    ]

    missing = [
        column for column in required
        if column not in history.columns
    ]

    if missing:
        raise ValueError(
            f"Missing history columns: {missing}"
        )

    if CONTACTS_FILE.exists():
        contacts = pd.read_csv(
            CONTACTS_FILE,
            dtype=str
        ).fillna("")
    else:
        contacts = pd.DataFrame()

    discovered_coverage = set()

    for _, contact in contacts.iterrows():

        role = infer_role(contact)

        if not role:
            continue

        domain = normalize(contact.get("company_domain", ""))
        company = normalize(contact.get("company_name", ""))

        company_key = domain if domain else company

        discovered_coverage.add((company_key, role))

    history["contacts_returned"] = pd.to_numeric(
        history["contacts_returned"],
        errors="coerce"
    ).fillna(0)

    zero_results = history[
        (history["status"] == "completed") &
        (history["contacts_returned"] == 0)
    ].copy()

    fallback_records = []
    skipped_discoveries = []

    for _, row in zero_results.iterrows():

        role = row["role_category"]

        if role not in FALLBACK_TITLES:
            continue

        domain = normalize(row["company_domain"])
        company = normalize(row["company_name"])

        company_key = domain if domain else company

        if (company_key, role) in discovered_coverage:

            skipped_discoveries.append({
                "company_name": row["company_name"],
                "role_category": role,
                "reason": "Prospect already discovered through another search"
            })

            continue

        fallback_records.append({
            "original_search_id": row["search_id"],
            "company_name": row["company_name"],
            "company_domain": row["company_domain"],
            "role_category": role,
            "fallback_job_titles": " | ".join(
                FALLBACK_TITLES[role]
            ),
            "fallback_title_count": len(FALLBACK_TITLES[role]),
            "fallback_status": "awaiting_approval",
            "contacts_returned_original": 0,
            "credits_charged_original": row.get(
                "credits_charged", 0
            )
        })

    result = pd.DataFrame(fallback_records)

    if not result.empty:

        result = result.drop_duplicates(
            subset=["original_search_id"],
            keep="last"
        ).reset_index(drop=True)

        result.insert(
            0,
            "fallback_id",
            [
                f"FALLBACK-{i:03d}"
                for i in range(1, len(result) + 1)
            ]
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nQUIKLEE LUSHA FALLBACK PLANNER")
    print("=" * 55)

    print("Historical zero-result searches:", len(zero_results))
    print("Existing discoveries matched:", len(skipped_discoveries))
    print("Fallback searches prepared:", len(result))

    if not result.empty:
        print("\nFallback queue:")
        print(
            result[
                [
                    "fallback_id",
                    "company_name",
                    "role_category",
                    "fallback_status"
                ]
            ].to_string(index=False)
        )
    else:
        print("\nNo fallback searches currently required.")

    print("\nExcluded because prospects already exist:")
    if skipped_discoveries:
        print(pd.DataFrame(skipped_discoveries).to_string(index=False))
    else:
        print("None")

    print("\nSaved:", OUTPUT_FILE)
    print("\nNo Lusha API requests were made.")
    print("No credits were consumed.")


if __name__ == "__main__":
    main()
