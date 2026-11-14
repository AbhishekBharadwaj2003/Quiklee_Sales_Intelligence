
from database.research_repository import get_company_research_history

companies = {
    4: "boAt",
    6: "The Whole Truth",
    7: "Snitch"
}

for company_id, company_name in companies.items():

    print("\n" + "=" * 60)
    print(f"RESEARCH RESULTS: {company_name}")
    print("=" * 60)

    records = get_company_research_history(company_id)

    if not records:
        print("No research records found.")
        continue

    for record in records:

        print("\nResearch Type:", record["research_type"])
        print("Source:", record["source"])
        print("Confidence:", record["confidence"])

        findings = record["findings"]

        if not isinstance(findings, dict):
            print("Findings unavailable.")
            continue

        print("\nWebsite Title:")
        print(findings.get("website_title", "Not available"))

        print("\nWebsite Description:")
        print(findings.get("website_description", "Not available"))

        print("\nSocial Links:")
        for platform, url in findings.get("social_links", {}).items():
            print(f"  {platform}: {url}")

        print("\nImportant Pages:")
        for page, url in findings.get("important_pages", {}).items():
            print(f"  {page}: {url}")

        products = findings.get("products", [])

        print(f"\nProducts extracted: {len(products)}")

        for product in products[:10]:
            print(
                f"  {product.get('product_name')} | "
                f"{product.get('displayed_price') or 'Price unavailable'}"
            )

        print("\nPage text length:")
        print(findings.get("page_text_length", 0))


print("\nRESEARCH RETRIEVAL COMPLETED.")
