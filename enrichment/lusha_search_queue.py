
import argparse
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CRM_FILE = PROJECT_ROOT / "data" / "Quiklee Sales CRM - Leads.csv"
VERIFIED_FILE = PROJECT_ROOT / "data" / "website_verification_results.csv"
TRAFFIC_FILE = PROJECT_ROOT / "data" / "traffic_enrichment_results.csv"

CONTACT_QUEUE_FILE = PROJECT_ROOT / "data" / "lusha_search_queue.csv"
COMPANY_QUEUE_FILE = PROJECT_ROOT / "data" / "lusha_company_search_queue.csv"

MINIMUM_MONTHLY_VISITS = 100000

TARGET_DESIGNATIONS = [
    "Operations Head",
    "Growth Head",
    "Supply Chain Head",
    "Marketplace Head / D2C Head"
]


def clean_value(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_name(value):
    return re.sub(
        r"[^a-z0-9]+", " ", clean_value(value).lower()
    ).strip()


def normalize_domain(value):
    value = clean_value(value).lower()

    if not value:
        return ""

    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]
    return value.removeprefix("www.")


def split_full_name(full_name):
    parts = clean_value(full_name).split()

    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], ""

    return parts[0], " ".join(parts[1:])


def load_crm(path):
    df = pd.read_csv(path)

    required = [
        "Brand Name",
        "Full Name",
        "Role",
        "Contact info ",
        "Email "
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing CRM columns: {missing}")

    return df


def load_website_lookup(path):
    df = pd.read_csv(path).fillna("")

    required = ["company_name", "verification_status"]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing website columns: {missing}")

    lookup = {}

    for _, row in df.iterrows():
        key = normalize_name(row["company_name"])

        if not key:
            continue

        website = clean_value(row.get("final_url")) or clean_value(
            row.get("candidate_website")
        )

        domain = normalize_domain(row.get("domain")) or normalize_domain(
            website
        )

        status = clean_value(row.get("verification_status"))

        lookup[key] = {
            "website": website,
            "domain": domain,
            "verification_status": status
        }

    return lookup


def load_traffic_lookup(path):
    if not path.exists():
        raise FileNotFoundError(f"Traffic results not found: {path}")

    df = pd.read_csv(path).fillna("")

    required = ["domain", "monthly_visits", "status"]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing traffic columns: {missing}")

    lookup = {}

    for _, row in df.iterrows():
        domain = normalize_domain(row.get("domain"))

        if not domain:
            continue

        visits = pd.to_numeric(
            pd.Series([row.get("monthly_visits")]),
            errors="coerce"
        ).iloc[0]

        status = clean_value(row.get("status"))

        # Keep the latest available record for each domain.
        lookup[domain] = {
            "monthly_visits": visits,
            "traffic_status": status
        }

    return lookup


def get_traffic_qualification(domain, traffic_lookup):
    traffic = traffic_lookup.get(domain)

    if not traffic:
        return "traffic_not_checked", None

    if traffic["traffic_status"] != "completed":
        return "traffic_lookup_failed", traffic["monthly_visits"]

    visits = traffic["monthly_visits"]

    if pd.isna(visits):
        return "traffic_data_missing", None

    if visits > MINIMUM_MONTHLY_VISITS:
        return "qualified_for_lusha", visits

    return "below_traffic_threshold", visits


def get_contact_priority(missing_email, missing_phone):
    if missing_email and missing_phone:
        return "A"
    if missing_email or missing_phone:
        return "B"
    return "C"


def prepare_queues(crm, website_lookup, traffic_lookup):

    contact_rows = []
    company_rows = []

    seen_companies = set()

    for index, row in crm.iterrows():

        company = clean_value(row.get("Brand Name"))
        full_name = clean_value(row.get("Full Name"))
        designation = clean_value(row.get("Role"))
        email = clean_value(row.get("Email "))
        phone = clean_value(row.get("Contact info "))

        first_name, last_name = split_full_name(full_name)

        company_key = normalize_name(company)
        website = website_lookup.get(company_key, {})

        domain = website.get("domain", "")
        verification = website.get(
            "verification_status", "not_verified"
        )

        visits_status, monthly_visits = get_traffic_qualification(
            domain, traffic_lookup
        )

        missing_email = not bool(email)
        missing_phone = not bool(phone)

        contact_priority = get_contact_priority(
            missing_email, missing_phone
        )

        if not company:
            contact_status = "missing_company"
        elif verification != "likely_company_match":
            contact_status = "website_needs_review"
        elif not domain:
            contact_status = "website_not_verified"
        elif visits_status != "qualified_for_lusha":
            contact_status = visits_status
        elif not full_name:
            contact_status = "missing_contact_name"
        elif not last_name:
            contact_status = "incomplete_contact_name"
        else:
            contact_status = "ready_for_lusha"

        contact_rows.append({
            "crm_row_number": index + 2,
            "company_name": company,
            "contact_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "existing_designation": designation,
            "website": website.get("website", ""),
            "company_domain": domain,
            "website_verification_status": verification,
            "monthly_visits": monthly_visits,
            "traffic_qualification": visits_status,
            "existing_email": email,
            "existing_phone": phone,
            "missing_email": missing_email,
            "missing_phone": missing_phone,
            "contact_priority": contact_priority,
            "queue_status": contact_status,
            "lusha_client_reference_id": f"crm-row-{index + 2}"
        })

        if company_key and company_key not in seen_companies:
            seen_companies.add(company_key)

            if not company:
                company_status = "missing_company"
            elif verification != "likely_company_match":
                company_status = "website_needs_review"
            elif not domain:
                company_status = "website_not_verified"
            elif visits_status != "qualified_for_lusha":
                company_status = visits_status
            else:
                company_status = "ready_for_lusha"

            company_rows.append({
                "company_name": company,
                "website": website.get("website", ""),
                "company_domain": domain,
                "website_verification_status": verification,
                "monthly_visits": monthly_visits,
                "traffic_qualification": visits_status,
                "company_queue_status": company_status,
                "target_role_1": TARGET_DESIGNATIONS[0],
                "target_role_2": TARGET_DESIGNATIONS[1],
                "target_role_3": TARGET_DESIGNATIONS[2],
                "target_role_4": TARGET_DESIGNATIONS[3]
            })

    return pd.DataFrame(contact_rows), pd.DataFrame(company_rows)


def print_summary(contacts, companies):

    print("\nQUIKLEE LUSHA QUALIFICATION QUEUE")
    print("=" * 55)

    print("CRM contact records:", len(contacts))
    print("Unique companies:", len(companies))

    print("\nCompany qualification:")

    for status, count in companies["company_queue_status"].value_counts().items():
        print(f"{status}: {count}")

    print("\nContact queue:")

    for status, count in contacts["queue_status"].value_counts().items():
        print(f"{status}: {count}")

    ready = companies[
        companies["company_queue_status"] == "ready_for_lusha"
    ]

    print("\nCOMPANIES READY FOR LUSHA:", len(ready))

    print("\nContact priority distribution:")

    for priority, count in contacts["contact_priority"].value_counts().sort_index().items():
        print(f"Priority {priority}: {count}")

    print("\nLusha target designation order:")

    for index, designation in enumerate(TARGET_DESIGNATIONS, start=1):
        print(f"{index}. {designation}")


def main():

    parser = argparse.ArgumentParser(
        description="Prepare traffic-qualified companies for Lusha."
    )

    parser.add_argument("--crm", default=str(CRM_FILE))
    parser.add_argument("--websites", default=str(VERIFIED_FILE))
    parser.add_argument("--traffic", default=str(TRAFFIC_FILE))
    parser.add_argument("--contact-output", default=str(CONTACT_QUEUE_FILE))
    parser.add_argument("--company-output", default=str(COMPANY_QUEUE_FILE))

    args = parser.parse_args()

    crm_path = Path(args.crm)
    website_path = Path(args.websites)
    traffic_path = Path(args.traffic)

    crm = load_crm(crm_path)
    websites = load_website_lookup(website_path)
    traffic = load_traffic_lookup(traffic_path)

    contacts, companies = prepare_queues(
        crm, websites, traffic
    )

    contact_output = Path(args.contact_output)
    company_output = Path(args.company_output)

    contact_output.parent.mkdir(parents=True, exist_ok=True)
    company_output.parent.mkdir(parents=True, exist_ok=True)

    contacts.to_csv(contact_output, index=False, encoding="utf-8-sig")
    companies.to_csv(company_output, index=False, encoding="utf-8-sig")

    print_summary(contacts, companies)

    print("\nContact queue saved:", contact_output)
    print("Company queue saved:", company_output)
    print("\nNo Lusha API requests were made.")


if __name__ == "__main__":
    main()
