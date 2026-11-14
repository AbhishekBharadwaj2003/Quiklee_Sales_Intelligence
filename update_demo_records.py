
from database.company_repository import (
    get_company_by_id,
    update_company
)

demo_companies = {
    3: {
        "company_name": "Mamaearth",
        "website_url": "https://mamaearth.in",
        "category": "Beauty and Personal Care",
        "description": "Indian beauty and personal care brand",
        "headquarters": "India"
    },
    4: {
        "company_name": "boAt",
        "website_url": "https://www.boat-lifestyle.com",
        "category": "Electronics",
        "description": "Indian consumer electronics and accessories brand",
        "headquarters": "India"
    },
    5: {
        "company_name": "Wakefit",
        "website_url": "https://www.wakefit.co",
        "category": "Home and Lifestyle",
        "description": "Indian home and sleep solutions brand",
        "headquarters": "India"
    },
    6: {
        "company_name": "The Whole Truth",
        "website_url": "https://thewholetruthfoods.com",
        "category": "Food and Beverages",
        "description": "Indian food and nutrition brand",
        "headquarters": "India"
    },
    7: {
        "company_name": "Snitch",
        "website_url": "https://www.snitch.co.in",
        "category": "Fashion and Apparel",
        "description": "Indian fashion and apparel brand",
        "headquarters": "India"
    }
}

print("\nUPDATING DEMO COMPANIES")
print("=" * 50)

for company_id, details in demo_companies.items():

    existing = get_company_by_id(company_id)

    if not existing:
        print(f"ID {company_id}: Record not found. Skipped.")
        continue

    success = update_company(company_id, details)

    if success:
        print(
            f"ID {company_id}: "
            f"{existing['company_name']} -> "
            f"{details['company_name']} | Updated"
        )
    else:
        print(f"ID {company_id}: Update failed.")

print("\nDATABASE UPDATE FINISHED.")
