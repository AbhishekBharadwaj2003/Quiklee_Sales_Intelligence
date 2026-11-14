
from pathlib import Path
import re

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = ROOT / "data" / "lusha_role_gap_analysis_v2.csv"
CONTACTS_FILE = ROOT / "data" / "lusha_discovered_contacts.csv"

OUTPUT_CSV = ROOT / "data" / "lusha_prospecting_plan.csv"
OUTPUT_EXCEL = ROOT / "reports" / "final" / "Lusha_Prospecting_Plan.xlsx"


ROLE_TITLES = {
    "operations_head": [
        "Chief Operating Officer",
        "Head of Operations",
        "Director of Operations",
        "Vice President of Operations"
    ],
    "growth_head": [
        "Head of Growth",
        "Growth Director",
        "Vice President of Growth"
    ],
    "supply_chain_head": [
        "Head of Supply Chain",
        "Head of Supply Chain Management",
        "Head of Supply Chain Operations",
        "supply chain director",
        "Vice President of Supply Chain",
        "Vice President of Supply Chain Management",
        "Vice President of Supply Chain Operations"
    ],
    "marketplace_ecommerce_head": [
        "E Commerce Director",
        "E Commerce Marketplace Manager",
        "E Commerce Business Manager",
        "E Commerce Operations Director"
    ]
}


ROLE_PRIORITY = {
    "operations_head": 1,
    "growth_head": 2,
    "supply_chain_head": 3,
    "marketplace_ecommerce_head": 4
}


ROLE_LABELS = {
    "operations_head": "Operations Head",
    "growth_head": "Growth Head",
    "supply_chain_head": "Supply Chain Head",
    "marketplace_ecommerce_head": "Marketplace / E-commerce"
}


def normalize(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower().strip()
    )


def load_discovered_contacts():

    if not CONTACTS_FILE.exists():
        return pd.DataFrame()

    return pd.read_csv(
        CONTACTS_FILE,
        dtype=str
    ).fillna("")


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Role-gap report not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE).fillna("")
    contacts = load_discovered_contacts()

    required = [
        "company_name",
        "company_domain",
        "missing_roles",
        "search_status"
    ]

    missing = [
        column for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns in role-gap report: {missing}"
        )

    discovered_coverage = set()
    verification_review = []

    for _, contact in contacts.iterrows():

        domain = normalize(contact.get("company_domain", ""))
        company = normalize(contact.get("company_name", ""))

        company_key = domain if domain else company

        title = str(contact.get("job_title", "")).lower()
        source = str(contact.get("discovery_source", "")).lower()

        role = None
        verification_status = "Discovered"

        if "growth" in title:
            role = "growth_head"

        elif "operation" in title:
            role = "operations_head"

        elif "supply chain" in title:
            role = "supply_chain_head"

        elif any(term in title for term in [
            "marketplace",
            "e-commerce",
            "e commerce",
            "d2c"
        ]):
            role = "marketplace_ecommerce_head"

        # General Manager is treated as an Operations prospect
        # only when discovered through our broader-title test.
        elif (
            "general manager" in title
            and "broader_title_test" in source
        ):
            role = "operations_head"
            verification_status = "Needs role verification"

        if role:

            discovered_coverage.add((company_key, role))

            if verification_status == "Needs role verification":
                verification_review.append({
                    "company_name": contact.get("company_name", ""),
                    "company_domain": contact.get("company_domain", ""),
                    "contact_name": contact.get("full_name", ""),
                    "job_title": contact.get("job_title", ""),
                    "role_category": ROLE_LABELS[role],
                    "linkedin_url": contact.get("linkedin_url", ""),
                    "review_status": "Verify operational responsibility",
                    "discovery_source": contact.get("discovery_source", "")
                })

    plan = []
    skipped = []

    qualified = df[
        df["search_status"] == "ready_for_role_search"
    ].copy()

    for _, company in qualified.iterrows():

        domain = normalize(company["company_domain"])
        company_name = normalize(company["company_name"])

        company_key = domain if domain else company_name

        missing_roles = [
            role.strip()
            for role in str(company["missing_roles"]).split("|")
            if role.strip()
        ]

        for role in missing_roles:

            if role not in ROLE_TITLES:
                continue

            if (company_key, role) in discovered_coverage:

                skipped.append({
                    "company": company["company_name"],
                    "role": ROLE_LABELS[role],
                    "reason": "Existing Lusha discovery"
                })

                continue

            plan.append({
                "priority": ROLE_PRIORITY[role],
                "company_name": company["company_name"],
                "company_domain": company["company_domain"],
                "role_category": ROLE_LABELS[role],
                "role_key": role,
                "verified_job_titles": " | ".join(
                    ROLE_TITLES[role]
                ),
                "number_of_titles": len(ROLE_TITLES[role]),
                "search_status": "planned",
                "contacts_discovered": 0,
                "credits_charged": 0,
                "manual_review_required": str(
                    company.get("manual_review_required", "")
                ).lower() in ("true", "1", "yes")
            })

    result = pd.DataFrame(plan)

    if not result.empty:

        result = result.sort_values(
            by=["priority", "company_name"],
            ascending=[True, True]
        ).reset_index(drop=True)

        result.insert(
            0,
            "search_id",
            [f"LUSHA-{i:03d}" for i in range(1, len(result) + 1)]
        )

    summary = (
        result.groupby("role_category")
        .agg(
            companies_to_search=("company_domain", "nunique"),
            planned_searches=("search_id", "count")
        )
        .reset_index()
        if not result.empty
        else pd.DataFrame(
            columns=[
                "role_category",
                "companies_to_search",
                "planned_searches"
            ]
        )
    )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_EXCEL.parent.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:

        result.to_excel(
            writer,
            sheet_name="Prospecting Plan",
            index=False
        )

        summary.to_excel(
            writer,
            sheet_name="Role Summary",
            index=False
        )

        pd.DataFrame(skipped).to_excel(
            writer,
            sheet_name="Already Discovered",
            index=False
        )

        pd.DataFrame(verification_review).to_excel(
            writer,
            sheet_name="Contact Verification",
            index=False
        )

    print("\nQUIKLEE LUSHA PROSPECTING PLAN")
    print("=" * 55)

    print("Qualified companies:", len(qualified))
    print("Existing role matches:", len(skipped))
    print("Contacts needing role verification:", len(verification_review))
    print("Remaining planned searches:", len(result))

    print("\nRole-wise search plan:")
    print(summary.to_string(index=False))

    print("\nAlready discovered roles:")
    if skipped:
        print(pd.DataFrame(skipped).to_string(index=False))
    else:
        print("None")

    print("\nContact verification queue:")
    if verification_review:
        print(
            pd.DataFrame(verification_review)[
                ["company_name", "contact_name", "job_title", "review_status"]
            ].to_string(index=False)
        )
    else:
        print("None")

    print("\nCSV:", OUTPUT_CSV)
    print("Excel:", OUTPUT_EXCEL)

    print("\nNo Lusha API requests were made.")
    print("No credits were consumed.")


if __name__ == "__main__":
    main()
