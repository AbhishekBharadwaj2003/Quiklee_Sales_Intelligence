
import json
from pathlib import Path

import pandas as pd


INPUT_FILE = Path("data/lusha_duroflex_growth_test.json")
OUTPUT_CSV = Path("data/lusha_discovered_contacts.csv")
OUTPUT_EXCEL = Path("reports/final/Lusha_Discovered_Contacts.xlsx")


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        response = json.load(file)

    results = response.get("results", [])

    if not results:
        print("No contacts found in the Lusha response.")
        return

    rows = []

    for contact in results:
        job = contact.get("jobTitle") or {}
        company = contact.get("company") or {}
        location = contact.get("location") or {}
        social = contact.get("socialLinks") or {}

        reveal_fields = contact.get("canReveal", [])

        email_info = next(
            (item for item in reveal_fields if item.get("field") == "emails"),
            {}
        )

        phone_info = next(
            (item for item in reveal_fields if item.get("field") == "phones"),
            {}
        )

        rows.append({
            "lusha_contact_id": contact.get("id"),
            "first_name": contact.get("firstName"),
            "last_name": contact.get("lastName"),
            "full_name": " ".join(filter(None, [
                contact.get("firstName"),
                contact.get("lastName")
            ])),
            "job_title": job.get("title"),
            "departments": ", ".join(job.get("departments", [])),
            "seniority": job.get("seniority"),
            "company_name": company.get("name"),
            "company_domain": company.get("domain"),
            "company_id": company.get("id"),
            "country": location.get("country"),
            "state": location.get("state"),
            "city": location.get("city"),
            "linkedin_url": social.get("linkedin"),
            "email_reveal_available": email_info.get("availability"),
            "email_reveal_credits": email_info.get("credits"),
            "phone_reveal_available": phone_info.get("availability"),
            "phone_reveal_credits": phone_info.get("credits"),
            "discovery_source": "Lusha Prospecting API",
            "discovery_status": "discovered_not_revealed"
        })

    df = pd.DataFrame(rows)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_EXCEL.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    billing = response.get("billing", {})

    summary = pd.DataFrame([
        {"Metric": "Contacts returned", "Value": billing.get("resultsReturned", len(rows))},
        {"Metric": "Credits charged", "Value": billing.get("creditsCharged")},
        {"Metric": "Company", "Value": "Duroflex"},
        {"Metric": "Search role", "Value": "Head of Growth"},
        {"Metric": "Company domain", "Value": "duroflexworld.com"}
    ])

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Discovered Contacts", index=False)
        summary.to_excel(writer, sheet_name="Search Summary", index=False)

    print("\nLusha contact export completed.")
    print(f"Contacts exported: {len(df)}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"Excel: {OUTPUT_EXCEL}")

    print("\nDiscovered contacts:")
    print(df[["full_name", "job_title", "company_name", "linkedin_url"]].to_string(index=False))


if __name__ == "__main__":
    main()
