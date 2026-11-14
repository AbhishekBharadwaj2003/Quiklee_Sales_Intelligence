
import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_FILE = PROJECT_ROOT / "data" / "Quiklee Sales CRM - Leads.csv"

TARGET_DESIGNATIONS = [
    "Founder",
    "Co-Founder",
    "CEO",
    "Chief Executive Officer",
    "Chief Operating Officer",
    "COO",
    "Head of Operations",
    "Operations Manager",
    "Head of E-commerce",
    "E-commerce Manager",
    "Supply Chain Manager",
    "Logistics Manager",
    "Business Development Manager"
]

COLUMN_MAPPING = {
    "company_name": "Brand Name",
    "website_url": "Website",
    "contact_name": "Full Name",
    "designation": "Role",
    "phone": "Contact info ",
    "email": "Email "
}


def clean_value(value):
    """Convert missing or whitespace-only values to an empty string."""

    if pd.isna(value):
        return ""

    return str(value).strip()


def load_company_dataset(file_path):
    """Load the existing CRM dataset without modifying its original columns."""

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {file_path}\n"
            "Place the CSV inside the project's data folder."
        )

    if file_path.suffix.lower() != ".csv":
        raise ValueError("Currently, only CSV files are supported.")

    dataframe = pd.read_csv(file_path)

    required_columns = [
        "Brand Name",
        "Website",
        "Full Name",
        "Role",
        "Contact info ",
        "Email "
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Required columns missing from dataset: {missing_columns}"
        )

    return dataframe


def needs_enrichment(company):
    """
    Return True if any important contact information is missing.

    Existing contact details are retained and are not overwritten here.
    """

    website = clean_value(company.get("website_url"))
    phone = clean_value(company.get("phone"))
    email = clean_value(company.get("email"))

    return not website or not phone or not email


def prepare_enrichment_queue(dataframe):
    """
    Prepare a queue containing companies with missing information.

    Every original CRM row is preserved. Duplicate brand names are
    not removed because they may represent separate CRM leads.
    """

    enrichment_queue = []

    for row_index, row in dataframe.iterrows():

        company = {
            "row_index": int(row_index),
            "company_name": clean_value(row.get("Brand Name")),
            "website_url": clean_value(row.get("Website")),
            "contact_name": clean_value(row.get("Full Name")),
            "designation": clean_value(row.get("Role")),
            "phone": clean_value(row.get("Contact info ")),
            "email": clean_value(row.get("Email ")),
            "target_designations": TARGET_DESIGNATIONS
        }

        if not company["company_name"]:
            continue

        if needs_enrichment(company):
            enrichment_queue.append(company)

    return enrichment_queue


def print_queue_summary(dataframe, enrichment_queue):
    """Display dataset and enrichment queue statistics."""

    total = len(dataframe)
    queued = len(enrichment_queue)

    website_missing = sum(
        not clean_value(value)
        for value in dataframe["Website"]
    )

    email_missing = sum(
        not clean_value(value)
        for value in dataframe["Email "]
    )

    phone_missing = sum(
        not clean_value(value)
        for value in dataframe["Contact info "]
    )

    print("\nQUIKLEE CONTACT ENRICHMENT")
    print("=" * 50)

    print(f"Total CRM records       : {total}")
    print(f"Records requiring work  : {queued}")
    print(f"Records with complete website, phone and email: {total - queued}")

    print("\nMISSING INFORMATION")
    print("-" * 50)
    print(f"Missing websites        : {website_missing}")
    print(f"Missing phone numbers   : {phone_missing}")
    print(f"Missing email addresses : {email_missing}")

    print("\nENRICHMENT QUEUE")
    print("-" * 50)

    for company in enrichment_queue[:15]:

        print(f"\nCompany: {company['company_name']}")
        print(f"Website: {company['website_url'] or 'Missing'}")
        print(f"Contact: {company['contact_name'] or 'Missing'}")
        print(f"Phone  : {company['phone'] or 'Missing'}")
        print(f"Email  : {company['email'] or 'Missing'}")

    if queued > 15:
        print(f"\n... and {queued - 15} more records.")

    print("\nQueue preparation completed.")


def main():
    parser = argparse.ArgumentParser(
        description="Prepare Quiklee CRM contact enrichment queue."
    )

    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_FILE),
        help="Path to the CRM CSV file."
    )

    args = parser.parse_args()

    try:
        dataframe = load_company_dataset(args.input)

        enrichment_queue = prepare_enrichment_queue(dataframe)

        print_queue_summary(dataframe, enrichment_queue)

    except Exception as error:
        print(f"\nERROR: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
