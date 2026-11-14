
from database.company_repository import get_all_companies
from database.research_repository import get_company_research_history


def main():
    companies = get_all_companies()

    for company in companies:
        if company["id"] not in (3, 4, 5, 6, 7):
            continue

        print("\n" + "=" * 65)
        print(f"COMPANY: {company['company_name']}")
        print(f"ID: {company['id']}")
        print(f"Research status: {company.get('research_status')}")

        records = get_company_research_history(company["id"])

        if not records:
            print("No research history found.")
            continue

        latest = records[0]
        findings = latest.get("findings", {})

        print("Research type:", latest.get("research_type"))
        print("Source:", latest.get("source"))
        print("Products found:", len(findings.get("products", [])))
        print("Research quality:", findings.get("research_quality"))
        print("Research status in findings:", findings.get("research_status"))
        print("Error:", findings.get("error"))
        print("Message:", findings.get("message"))


if __name__ == "__main__":
    main()
