
from pathlib import Path
import json

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

RAW_FILE = (
    ROOT / "data" / "lusha_prospecting" /
    "raw_responses" / "BACCABUCCI-OPERATIONS-BROAD.json"
)

CSV_FILE = ROOT / "data" / "lusha_discovered_contacts.csv"

EXCEL_FILE = (
    ROOT / "reports" / "final" /
    "Lusha_Discovered_Contacts.xlsx"
)


COLUMNS = [
    "lusha_contact_id",
    "first_name",
    "last_name",
    "full_name",
    "job_title",
    "departments",
    "seniority",
    "company_name",
    "company_domain",
    "company_id",
    "country",
    "state",
    "city",
    "linkedin_url",
    "email_reveal_available",
    "email_reveal_credits",
    "phone_reveal_available",
    "phone_reveal_credits",
    "discovery_source",
    "discovery_status"
]


def extract_contact(contact):

    job = contact.get("jobTitle") or {}
    company = contact.get("company") or {}
    location = contact.get("location") or {}
    social = contact.get("socialLinks") or {}

    reveal = {
        item.get("field"): item
        for item in contact.get("canReveal", [])
    }

    first_name = contact.get("firstName", "")
    last_name = contact.get("lastName", "")

    full_name = " ".join(
        value for value in [first_name, last_name] if value
    )

    return {
        "lusha_contact_id": contact.get("id", ""),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "job_title": job.get("title", ""),
        "departments": " | ".join(job.get("departments", [])),
        "seniority": job.get("seniority", ""),
        "company_name": company.get("name", ""),
        "company_domain": company.get("domain", ""),
        "company_id": company.get("id", ""),
        "country": location.get("country", ""),
        "state": location.get("state", ""),
        "city": location.get("city", ""),
        "linkedin_url": social.get("linkedin", ""),
        "email_reveal_available": (
            reveal.get("emails", {}).get("availability", "") == "available"
        ),
        "email_reveal_credits": reveal.get("emails", {}).get("credits", 0),
        "phone_reveal_available": (
            reveal.get("phones", {}).get("availability", "") == "available"
        ),
        "phone_reveal_credits": reveal.get("phones", {}).get("credits", 0),
        "discovery_source": "lusha_prospecting_broader_title_test",
        "discovery_status": "discovered_not_revealed"
    }


def main():

    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Raw response not found: {RAW_FILE}")

    with open(RAW_FILE, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    response = raw_data.get("response", {})
    contacts = response.get("results", [])

    if not contacts:
        print("No contacts found in the API response.")
        return

    new_records = pd.DataFrame(
        [extract_contact(contact) for contact in contacts],
        columns=COLUMNS
    )

    if CSV_FILE.exists():
        existing = pd.read_csv(CSV_FILE, dtype=str).fillna("")
    else:
        existing = pd.DataFrame(columns=COLUMNS)

    for column in COLUMNS:
        if column not in existing.columns:
            existing[column] = ""

    existing_ids = set(
        existing["lusha_contact_id"].astype(str)
    )

    new_records = new_records[
        ~new_records["lusha_contact_id"].astype(str).isin(existing_ids)
    ]

    if new_records.empty:
        print("All contacts from this response already exist.")
        return

    updated = pd.concat(
        [existing, new_records],
        ignore_index=True
    )

    updated = updated.drop_duplicates(
        subset=["lusha_contact_id"],
        keep="first"
    )

    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXCEL_FILE.parent.mkdir(parents=True, exist_ok=True)

    updated.to_csv(
        CSV_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl") as writer:

        updated.to_excel(
            writer,
            sheet_name="Discovered Contacts",
            index=False
        )

    print("\nLUSHA CONTACT INTEGRATION COMPLETE")
    print("=" * 50)

    print("New contacts added:", len(new_records))
    print("Total unique contacts:", len(updated))

    print("\nNew contacts:")

    for _, row in new_records.iterrows():
        print(
            f"{row['full_name']} | "
            f"{row['job_title']} | "
            f"{row['company_name']}"
        )

    print("\nUpdated CSV:", CSV_FILE)
    print("Updated Excel:", EXCEL_FILE)


if __name__ == "__main__":
    main()
