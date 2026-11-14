from collections import Counter

from database.research_repository import get_company_research_history


def main():
    records = get_company_research_history(7)

    if not records:
        print("No research records found.")
        return

    products = records[0].get("findings", {}).get("products", [])
    total = len(products)

    print("=" * 50)
    print("SNITCH PRODUCT DATA QUALITY REPORT")
    print("=" * 50)

    print(f"\nTotal products: {total}")

    fields = [
        "product_name",
        "displayed_price",
        "mrp",
        "product_url",
        "sku",
        "category",
    ]

    print("\nFIELD COMPLETENESS")

    for field in fields:
        populated = sum(
            1 for product in products
            if product.get(field) not in (None, "", "N/A")
        )

        print(f"{field}: {populated}/{total}")

    skus = [
        product.get("sku")
        for product in products
        if product.get("sku")
    ]

    print("\nDATA QUALITY CHECKS")
    print(f"Duplicate SKUs: {len(skus) - len(set(skus))}")

    print(
        "Missing product names:",
        sum(not product.get("product_name") for product in products)
    )

    print(
        "Missing product URLs:",
        sum(not product.get("product_url") for product in products)
    )

    print(
        "Zero or missing prices:",
        sum(
            not product.get("displayed_price")
            or float(product.get("displayed_price") or 0) <= 0
            for product in products
        )
    )

    print("\nCATEGORY DISTRIBUTION")

    categories = Counter(
        product.get("category") or "Unknown"
        for product in products
    )

    for category, count in categories.most_common():
        print(f"{category}: {count}")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()