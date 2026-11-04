from database.company_repository import get_all_companies
from database.contact_repository import get_company_contacts


TARGET_DESIGNATIONS = [
    "Founder",
    "Co-Founder",
    "CEO",
    "Chief Operating Officer",
    "Head of Operations",
    "Operations Manager",
    "Head of E-commerce",
    "E-commerce Manager",
    "Supply Chain Manager",
    "Logistics Manager",
    "Business Development Manager"
]


def needs_enrichment(company_id):
    """
    Check whether a company already has contact information.
    """

    contacts = get_company_contacts(company_id)

    if contacts:
        return False

    return True


def prepare_enrichment_queue():
    """
    Identify companies that need contact enrichment.
    """

    companies = get_all_companies()

    enrichment_queue = []

    for company in companies:

        company_id = company["id"]

        if not needs_enrichment(company_id):

            print(
                f"Skipping {company['company_name']}: "
                "contact already exists."
            )
            continue

        enrichment_queue.append({
            "company_id": company_id,
            "company_name": company["company_name"],
            "website_url": company["website_url"],
            "target_designations": TARGET_DESIGNATIONS
        })

    return enrichment_queue


if __name__ == "__main__":

    print("\nCONTACT ENRICHMENT WORKFLOW")
    print("-" * 40)

    queue = prepare_enrichment_queue()

    print(f"\nCompanies requiring enrichment: {len(queue)}")

    for company in queue:

        print("\nCompany:", company["company_name"])
        print("Website:", company["website_url"])
        print("Target roles:")

        for designation in company["target_designations"]:
            print("-", designation)