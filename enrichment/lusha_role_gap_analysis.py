
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "lusha_search_queue.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "lusha_role_gap_analysis.csv"

ROLE_KEYWORDS = {
    "operations_head": [
        "operations head",
        "head of operations",
        "head ops",
        "ops head",
        "chief operating officer",
        "coo",
        "operations director",
        "senior operations"
    ],
    "growth_head": [
        "growth head",
        "head of growth",
        "growth director",
        "chief growth officer",
        "growth lead",
        "vp growth",
        "vice president growth"
    ],
    "supply_chain_head": [
        "supply chain",
        "head of logistics",
        "logistics head",
        "procurement head",
        "head of procurement"
    ],
    "marketplace_head": [
        "marketplace head",
        "head of marketplace",
        "marketplace director",
        "marketplace lead",
        "ecommerce head",
        "e-commerce head",
        "head of ecommerce",
        "head of e-commerce"
    ],
    "d2c_head": [
        "d2c head",
        "head of d2c",
        "d2c director",
        "direct to consumer",
        "head of direct to consumer"
    ]
}


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_name(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean(value).lower()
    ).strip()


def normalize_designation(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean(value).lower()
    ).strip()


def classify_roles(designation):
    """
    Identify explicit role matches.
    Founder, CEO and generic Director titles are not
    automatically classified into functional roles.
    """

    title = normalize_designation(designation)
    matched_roles = []

    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = normalize_designation(keyword)

            if normalized_keyword in title:
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

    qualified["company_key"] = (
        qualified["company_domain"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    qualified.loc[
        qualified["company_key"] == "",
        "company_key"
    ] = qualified["company_name"].apply(normalize_name)

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
                normalize_name(name),
                email.lower()
            )

            if contact_key not in seen_contacts:
                seen_contacts.add(contact_key)

                existing_contacts.append(
                    f"{name} | {designation} | {email or 'No email'}"
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

            # Flag email/name inconsistencies for manual review.
            if email and name:
                email_local = email.split("@")[0]
                email_name = normalize_name(
                    email_local.replace(".", " ").replace("_", " ")
                )

                name_tokens = normalize_name(name).split()

                if (
                    len(name_tokens) >= 2
                    and not all(token in email_name for token in name_tokens)
                    and not all(token in email_name for token in name_tokens[-1:])
                ):
                    manual_review_flags.append(
                        f"Verify name/email match: {name}"
                    )

        role_status = {}

        for role in ROLE_KEYWORDS:

            is_covered = role in covered_roles

            role_status[role] = (
                "covered" if is_covered else "search_needed"
            )

        missing_roles = [
            role for role, status in role_status.items()
            if status == "search_needed"
        ]

        results.append({
            "company_name": company_name,
            "company_domain": domain,
            "existing_contact_count": len(existing_contacts),
            "existing_contacts": " || ".join(existing_contacts),

            "operations_head_status": role_status["operations_head"],
            "growth_head_status": role_status["growth_head"],
            "supply_chain_head_status": role_status["supply_chain_head"],
            "marketplace_head_status": role_status["marketplace_head"],
            "d2c_head_status": role_status["d2c_head"],

            "missing_roles": ", ".join(missing_roles),
            "roles_to_search": len(missing_roles),

            "manual_review_required": bool(manual_review_flags),
            "manual_review_notes": " || ".join(
                sorted(set(manual_review_flags))
            )
        })

    return pd.DataFrame(results)


def print_summary(report):

    print("\nQUIKLEE LUSHA ROLE GAP ANALYSIS")
    print("=" * 60)

    print("Unique qualified companies:", len(report))

    print("\nRole coverage:")

    role_columns = {
        "Operations Head": "operations_head_status",
        "Growth Head": "growth_head_status",
        "Supply Chain Head": "supply_chain_head_status",
        "Marketplace Head": "marketplace_head_status",
        "D2C Head": "d2c_head_status"
    }

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
        "Total missing role searches:",
        int(report["roles_to_search"].sum())
    )

    print("\nFirst 10 companies:")

    columns = [
        "company_name",
        "operations_head_status",
        "growth_head_status",
        "supply_chain_head_status",
        "marketplace_head_status",
        "d2c_head_status"
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

    print("\nNo API requests were made.")


if __name__ == "__main__":
    main()
