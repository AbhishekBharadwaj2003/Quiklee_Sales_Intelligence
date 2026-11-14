
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "lusha_search_queue.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "lusha_role_gap_analysis_v2.csv"

# Verified Lusha role categories and title variations.
ROLE_KEYWORDS = {
    "operations_head": [
        "operations head",
        "head of operations",
        "head ops",
        "ops head",
        "chief operating officer",
        "coo",
        "director of operations",
        "operations director",
        "vice president of operations",
        "vp operations",
        "head of operations management"
    ],

    "growth_head": [
        "growth head",
        "head of growth",
        "growth director",
        "chief growth officer",
        "growth lead",
        "vice president of growth",
        "vp growth"
    ],

    "supply_chain_head": [
        "supply chain",
        "head of logistics",
        "logistics head",
        "procurement head",
        "head of procurement",
        "supply chain director",
        "vice president of supply chain"
    ],

    "marketplace_ecommerce_head": [
        "marketplace head",
        "head of marketplace",
        "marketplace director",
        "marketplace lead",
        "e commerce director",
        "e commerce marketplace manager",
        "e commerce business manager",
        "e commerce operations director",
        "ecommerce director",
        "ecommerce manager",
        "head of ecommerce",
        "head of e commerce",
        "head of d2c",
        "d2c head",
        "d2c director",
        "direct to consumer"
    ]
}


ROLE_TITLES_FOR_LUSHA = {
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


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean(value).lower()
    ).strip()


def normalize_domain(value):
    value = clean(value).lower()

    if not value:
        return ""

    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]

    return value.removeprefix("www.")


def classify_roles(designation):
    title = normalize(designation)
    matched_roles = []

    if not title:
        return matched_roles

    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = normalize(keyword)

            # Match complete normalized phrases.
            if f" {normalized_keyword} " in f" {title} ":
                matched_roles.append(role)
                break

    return matched_roles


def load_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Lusha queue not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE).fillna("")

    required = [
        "company_name",
        "contact_name",
        "existing_designation",
        "existing_email",
        "existing_phone",
        "company_domain",
        "queue_status"
    ]

    missing = [
        column for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    return df


def analyze_companies(df):

    qualified = df[
        df["queue_status"].astype(str)
        == "ready_for_lusha"
    ].copy()

    qualified["company_domain"] = (
        qualified["company_domain"]
        .apply(normalize_domain)
    )

    qualified["company_key"] = qualified.apply(
        lambda row: (
            row["company_domain"]
            or normalize(row["company_name"])
        ),
        axis=1
    )

    results = []

    for company_key, group in qualified.groupby(
        "company_key",
        sort=False
    ):

        company_name = clean(
            group.iloc[0]["company_name"]
        )

        domain = clean(
            group.iloc[0]["company_domain"]
        )

        existing_contacts = []
        covered_roles = set()
        manual_review_flags = []

        seen_contacts = set()

        for _, contact in group.iterrows():

            name = clean(contact["contact_name"])
            designation = clean(
                contact["existing_designation"]
            )
            email = clean(contact["existing_email"])
            phone = clean(contact["existing_phone"])

            contact_key = (
                normalize(name),
                email.lower()
            )

            if contact_key not in seen_contacts:
                seen_contacts.add(contact_key)

                existing_contacts.append(
                    f"{name} | {designation} | "
                    f"{email or 'No email'} | "
                    f"{phone or 'No phone'}"
                )

            if not name or not designation:
                manual_review_flags.append(
                    "Incomplete contact information"
                )

            matched_roles = classify_roles(designation)
            covered_roles.update(matched_roles)

            if not email:
                manual_review_flags.append(
                    f"Missing email: {name or 'Unknown contact'}"
                )

            # Flag only clear structural mismatches.
            if email and "@" in email and domain:
                email_domain = email.rsplit("@", 1)[-1].lower()

                if email_domain != domain:
                    manual_review_flags.append(
                        f"Email domain differs from company domain: {name}"
                    )

        role_status = {}

        for role in ROLE_KEYWORDS:
            role_status[role] = (
                "covered"
                if role in covered_roles
                else "search_needed"
            )

        missing_roles = [
            role
            for role, status in role_status.items()
            if status == "search_needed"
        ]

        roles_to_search = [
            {
                "role_category": role,
                "verified_job_titles": ROLE_TITLES_FOR_LUSHA[role]
            }
            for role in missing_roles
        ]

        results.append({
            "company_name": company_name,
            "company_domain": domain,
            "existing_contact_count": len(existing_contacts),
            "existing_contacts": " || ".join(existing_contacts),

            "operations_head_status": role_status["operations_head"],
            "growth_head_status": role_status["growth_head"],
            "supply_chain_head_status": role_status["supply_chain_head"],
            "marketplace_ecommerce_status": role_status[
                "marketplace_ecommerce_head"
            ],

            "missing_roles": " | ".join(missing_roles),
            "number_of_roles_to_search": len(missing_roles),

            "roles_to_search": " || ".join(
                f"{item['role_category']}: "
                f"{', '.join(item['verified_job_titles'])}"
                for item in roles_to_search
            ),

            "manual_review_required": bool(manual_review_flags),
            "manual_review_notes": " || ".join(
                sorted(set(manual_review_flags))
            ),

            "search_status": (
                "ready_for_role_search"
                if missing_roles
                else "all_target_roles_covered"
            )
        })

    return pd.DataFrame(results)


def print_summary(report):

    print("\nQUIKLEE LUSHA ROLE GAP ANALYSIS V2")
    print("=" * 65)

    print("Unique qualified companies:", len(report))

    role_columns = {
        "Operations Head": "operations_head_status",
        "Growth Head": "growth_head_status",
        "Supply Chain Head": "supply_chain_head_status",
        "Marketplace / E-commerce": "marketplace_ecommerce_status"
    }

    print("\nROLE COVERAGE")

    for role, column in role_columns.items():

        covered = int(
            (report[column] == "covered").sum()
        )

        missing = int(
            (report[column] == "search_needed").sum()
        )

        print(
            f"{role}: Covered {covered} | Search needed {missing}"
        )

    print(
        "\nCompanies requiring manual review:",
        int(report["manual_review_required"].sum())
    )

    print(
        "Companies with roles to search:",
        int(
            (report["search_status"] == "ready_for_role_search").sum()
        )
    )

    print(
        "Companies with all roles covered:",
        int(
            (report["search_status"] == "all_target_roles_covered").sum()
        )
    )

    print("\nSEARCH QUEUE PREVIEW")

    columns = [
        "company_name",
        "company_domain",
        "missing_roles",
        "number_of_roles_to_search",
        "search_status"
    ]

    print(
        report[columns].head(10).to_string(index=False)
    )


def main():

    df = load_data()
    report = analyze_companies(df)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print_summary(report)

    print("\nReport saved:")
    print(OUTPUT_FILE)

    print("\nNo Lusha API requests were made.")


if __name__ == "__main__":
    main()
