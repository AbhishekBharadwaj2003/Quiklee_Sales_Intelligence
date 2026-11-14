
import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CRM_FILE = PROJECT_ROOT / "data" / "Quiklee Sales CRM - Leads.csv"

LUSHA_FILE = PROJECT_ROOT / "data" / "lusha_search_results.json"

OUTPUT_FILE = PROJECT_ROOT / "reports" / "lusha_contact_comparison.xlsx"


def clean_value(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_name(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_value(value).lower()
    ).strip()


def normalize_phone(value):
    return re.sub(r"\D", "", clean_value(value))


def load_crm():
    if not CRM_FILE.exists():
        raise FileNotFoundError(
            f"CRM file not found: {CRM_FILE}"
        )

    dataframe = pd.read_csv(CRM_FILE)

    required_columns = [
        "Brand Name",
        "Full Name",
        "Role",
        "Contact info ",
        "Email "
    ]

    missing = [
        column for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"Missing CRM columns: {missing}"
        )

    return dataframe


def load_lusha_results():
    if not LUSHA_FILE.exists():
        raise FileNotFoundError(
            f"Lusha response file not found: {LUSHA_FILE}"
        )

    with open(
        LUSHA_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def find_crm_contact(dataframe, result):
    first_name = clean_value(result.get("firstName"))
    last_name = clean_value(result.get("lastName"))

    lusha_name = normalize_name(
        f"{first_name} {last_name}"
    )

    company = normalize_name(
        result.get("company", {}).get("name", "")
    )

    if not lusha_name:
        return None

    matches = []

    for index, row in dataframe.iterrows():

        crm_name = normalize_name(
            row.get("Full Name", "")
        )

        crm_company = normalize_name(
            row.get("Brand Name", "")
        )

        if crm_name != lusha_name:
            continue

        company_matches = (
            crm_company == company
            or crm_company in company
            or company in crm_company
        )

        if company_matches:
            matches.append((index, row))

    if len(matches) == 1:
        return matches[0]

    return None


def compare_contact(crm_row, result):

    crm_role = clean_value(
        crm_row.get("Role")
    )

    crm_email = clean_value(
        crm_row.get("Email ")
    )

    crm_phone = clean_value(
        crm_row.get("Contact info ")
    )

    lusha_job = result.get("jobTitle", {})

    lusha_role = clean_value(
        lusha_job.get("title", "")
    )

    lusha_company = result.get("company", {})

    social_links = result.get("socialLinks", {})

    lusha_linkedin = clean_value(
        social_links.get("linkedin", "")
    )

    location = result.get("location", {})

    can_reveal = result.get("canReveal", [])

    available_reveals = "; ".join(
        item.get("field", "")
        for item in can_reveal
        if item.get("availability") == "available"
    )

    if crm_role and lusha_role:

        if normalize_name(crm_role) == normalize_name(lusha_role):
            role_status = "match"
        else:
            role_status = "designation_mismatch"

    elif lusha_role:
        role_status = "CRM designation missing"

    else:
        role_status = "Lusha designation unavailable"

    return {
        "CRM Company": clean_value(
            crm_row.get("Brand Name")
        ),
        "CRM Contact Name": clean_value(
            crm_row.get("Full Name")
        ),
        "CRM Designation": crm_role,
        "Lusha Designation": lusha_role,
        "Designation Comparison": role_status,
        "CRM Email": crm_email,
        "CRM Phone": crm_phone,
        "Lusha Email": "Not returned in search response",
        "Lusha Phone": "Not revealed",
        "Lusha Company": clean_value(
            lusha_company.get("name", "")
        ),
        "Lusha Company Domain": clean_value(
            lusha_company.get("domain", "")
        ),
        "Lusha LinkedIn": lusha_linkedin,
        "Lusha Department": "; ".join(
            lusha_job.get("departments", [])
        ),
        "Lusha Seniority": clean_value(
            lusha_job.get("seniority", "")
        ),
        "Lusha City": clean_value(
            location.get("city", "")
        ),
        "Lusha State": clean_value(
            location.get("state", "")
        ),
        "Lusha Country": clean_value(
            location.get("country", "")
        ),
        "Available Reveal Fields": available_reveals,
        "Lusha Profile ID": clean_value(
            result.get("id", "")
        ),
        "Match Status": "Matched"
    }


def main():

    print("\nQUIKLEE LUSHA RESULT PROCESSOR")
    print("=" * 55)

    crm = load_crm()
    lusha_data = load_lusha_results()

    results = lusha_data.get("results", [])

    if not results:
        print("No Lusha results found.")
        return

    comparison_records = []
    unmatched_records = []

    for result in results:

        match = find_crm_contact(
            crm,
            result
        )

        if match is None:

            unmatched_records.append({
                "Lusha Name": (
                    clean_value(result.get("firstName"))
                    + " "
                    + clean_value(result.get("lastName"))
                ).strip(),
                "Lusha Company": clean_value(
                    result.get("company", {}).get("name", "")
                ),
                "Lusha Profile ID": clean_value(
                    result.get("id", "")
                ),
                "Match Status": "CRM match not found or ambiguous"
            })

            continue

        _, crm_row = match

        comparison_records.append(
            compare_contact(
                crm_row,
                result
            )
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    comparison_df = pd.DataFrame(
        comparison_records
    )

    unmatched_df = pd.DataFrame(
        unmatched_records
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl"
    ) as writer:

        comparison_df.to_excel(
            writer,
            sheet_name="Contact Comparison",
            index=False
        )

        unmatched_df.to_excel(
            writer,
            sheet_name="Unmatched Results",
            index=False
        )

    print("Lusha results received:", len(results))
    print("CRM contacts matched:", len(comparison_records))
    print("Unmatched results:", len(unmatched_records))

    if not comparison_df.empty:

        mismatches = (
            comparison_df["Designation Comparison"]
            == "designation_mismatch"
        ).sum()

        print("Designation mismatches:", mismatches)

    print("\nExcel report generated:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()
