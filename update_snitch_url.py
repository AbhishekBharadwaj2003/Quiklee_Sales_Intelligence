from database.company_repository import (
    get_company_by_id,
    update_company
)

company_id = 7
new_url = "https://www.snitch.com"

company = get_company_by_id(company_id)

if not company:
    print("Snitch record not found.")
else:
    success = update_company(
        company_id,
        {
            "website_url": new_url
        }
    )

    if success:
        print("Snitch website updated successfully.")
        print("Company:", company["company_name"])
        print("New website:", new_url)
    else:
        print("Update failed.")