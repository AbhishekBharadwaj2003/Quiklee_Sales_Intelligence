
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT / "data" / "lusha_search_queue.csv"
GAP_FILE = ROOT / "data" / "lusha_role_gap_analysis.csv"

COMPANY_OUTPUT = ROOT / "data" / "lusha_final_company_queue.csv"
CONTACT_OUTPUT = ROOT / "data" / "lusha_final_contact_audit.csv"


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize(value):
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def unique_values(values):
    result = []
    seen = set()

    for value in values:
        value = clean(value)

        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)

    return result


def load_inputs():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(QUEUE_FILE)

    if not GAP_FILE.exists():
        raise FileNotFoundError(GAP_FILE)

    # Avoid fillna("") on mixed numeric columns.
    queue = pd.read_csv(QUEUE_FILE, dtype=str).fillna("")
    gaps = pd.read_csv(GAP_FILE, dtype=str).fillna("")

    required_queue = [
        "company_name",
        "company_domain",
        "contact_name",
        "existing_designation",
        "existing_email",
        "existing_phone",
        "queue_status"
    ]

    missing = [
        col for col in required_queue
        if col not in queue.columns
    ]

    if missing:
        raise ValueError(
            f"Missing queue columns: {missing}"
        )

    required_gaps = [
        "company_domain",
        "operations_head_status",
        "growth_head_status",
        "supply_chain_head_status",
        "marketplace_head_status",
        "d2c_head_status"
    ]

    missing = [
        col for col in required_gaps
        if col not in gaps.columns
    ]

    if missing:
        raise ValueError(
            f"Missing role-gap columns: {missing}"
        )

    return queue, gaps


def build_company_queue(queue, gaps):

    ready = queue[
        queue["queue_status"].str.lower()
        == "ready_for_lusha"
    ].copy()

    ready["company_key"] = ready.apply(
        lambda row: (
            normalize(row["company_domain"])
            or normalize(row["company_name"])
        ),
        axis=1
    )

    gaps["company_key"] = gaps.apply(
        lambda row: (
            normalize(row["company_domain"])
            or normalize(row["company_name"])
        ),
        axis=1
    )

    gap_lookup = {
        row["company_key"]: row
        for _, row in gaps.iterrows()
    }

    company_rows = []
    contact_rows = []

    for company_key, group in ready.groupby(
        "company_key",
        sort=False
    ):

        first = group.iloc[0]

        company_name = clean(first["company_name"])
        domain = clean(first["company_domain"])

        gap = gap_lookup.get(company_key)

        if gap is None:
            raise ValueError(
                f"No role-gap record found for {company_name} ({domain})"
            )

        contacts = []
        seen_contacts = set()

        for _, row in group.iterrows():

            name = clean(row["contact_name"])
            designation = clean(row["existing_designation"])
            email = clean(row["existing_email"])
            phone = clean(row["existing_phone"])

            contact_key = (
                normalize(name),
                email.lower(),
                re.sub(r"\D", "", phone)
            )

            if contact_key not in seen_contacts:
                seen_contacts.add(contact_key)

                contacts.append(
                    {
                        "company_name": company_name,
                        "company_domain": domain,
                        "contact_name": name,
                        "existing_designation": designation,
                        "existing_email": email,
                        "existing_phone": phone,
                    }
                )

            contact_rows.append(
                {
                    "company_name": clean(row["company_name"]),
                    "company_domain": clean(row["company_domain"]),
                    "contact_name": name,
                    "existing_designation": designation,
                    "existing_email": email,
                    "existing_phone": phone,
                    "queue_status": clean(row["queue_status"]),
                }
            )

        operations = clean(gap["operations_head_status"])
        growth = clean(gap["growth_head_status"])
        supply_chain = clean(gap["supply_chain_head_status"])
        marketplace = clean(gap["marketplace_head_status"])
        d2c = clean(gap["d2c_head_status"])

        marketplace_d2c = (
            "covered"
            if "covered" in {marketplace, d2c}
            else "search_needed"
        )

        role_status = [
            ("Operations Head", operations),
            ("Growth Head", growth),
            ("Supply Chain Head", supply_chain),
            ("Marketplace Head / D2C Head", marketplace_d2c),
        ]

        missing_roles = [
            role
            for role, status in role_status
            if status != "covered"
        ]

        manual_review = clean(
            gap.get("manual_review_required", "")
        ).lower() in {"true", "1", "yes"}

        manual_notes = clean(
            gap.get("manual_review_notes", "")
        )

        company_rows.append(
            {
                "company_name": company_name,
                "company_domain": domain,
                "existing_contact_count": len(contacts),
                "existing_contacts": " || ".join(
                    f"{c['contact_name']} | "
                    f"{c['existing_designation']} | "
                    f"{c['existing_email'] or 'No email'} | "
                    f"{c['existing_phone'] or 'No phone'}"
                    for c in contacts
                ),

                "operations_head_status": operations,
                "growth_head_status": growth,
                "supply_chain_head_status": supply_chain,
                "marketplace_d2c_status": marketplace_d2c,

                "roles_to_search": " | ".join(missing_roles),
                "number_of_role_categories_to_search": len(
                    missing_roles
                ),

                "manual_review_required": manual_review,
                "manual_review_notes": manual_notes,

                "lusha_search_status": (
                    "ready_for_role_search"
                    if missing_roles
                    else "existing_roles_covered"
                )
            }
        )

    return (
        pd.DataFrame(company_rows),
        pd.DataFrame(contact_rows)
    )


def main():

    queue, gaps = load_inputs()

    companies, contacts = build_company_queue(
        queue,
        gaps
    )

    companies.to_csv(
        COMPANY_OUTPUT,
        index=False,
        encoding="utf-8-sig"
    )

    contacts.to_csv(
        CONTACT_OUTPUT,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nQUIKLEE FINAL LUSHA SEARCH QUEUE")
    print("=" * 55)

    print("Qualified CRM rows:", len(
        queue[queue["queue_status"] == "ready_for_lusha"]
    ))

    print("Unique companies:", len(companies))
    print("Contact audit rows:", len(contacts))

    print("\nRole categories requiring searches:")

    role_columns = {
        "Operations Head": "operations_head_status",
        "Growth Head": "growth_head_status",
        "Supply Chain Head": "supply_chain_head_status",
        "Marketplace Head / D2C Head": "marketplace_d2c_status",
    }

    for role, column in role_columns.items():
        count = int(
            (companies[column] != "covered").sum()
        )
        print(f"{role}: {count}")

    print(
        "\nCompanies requiring manual review:",
        int(companies["manual_review_required"].sum())
    )

    print("\nLusha search status:")
    print(
        companies["lusha_search_status"]
        .value_counts()
        .to_string()
    )

    print("\nCompany queue saved:")
    print(COMPANY_OUTPUT)

    print("\nContact audit saved:")
    print(CONTACT_OUTPUT)

    print("\nNo Lusha API requests were made.")


if __name__ == "__main__":
    main()
