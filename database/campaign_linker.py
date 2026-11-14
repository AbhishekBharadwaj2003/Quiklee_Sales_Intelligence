
from database.db import get_db
from database.company_repository import add_company, get_company_by_id


def link_campaign_companies(campaign_id):
    """
    Link campaign records to existing companies.

    Existing companies are reused through the company repository's
    domain/name deduplication logic.

    Duplicate source rows remain separate campaign records.
    No external APIs are called.
    """

    with get_db() as connection:
        records = connection.execute(
            """
            SELECT
                id,
                source_brand_name,
                website
            FROM campaign_records
            WHERE campaign_id = ?
            ORDER BY source_row_number
            """,
            (campaign_id,),
        ).fetchall()

    linked_count = 0
    created_count = 0
    existing_count = 0
    failed_count = 0

    for record in records:

        record_id = record["id"]
        brand_name = record["source_brand_name"]
        website = record["website"] or ""

        try:
            result = add_company({
                "company_name": brand_name,
                "website_url": website,
                "validation_status": "pending",
            })

            company_id = result.get("company_id")

            if not company_id:
                failed_count += 1
                continue

            if result.get("success"):
                created_count += 1
            else:
                existing_count += 1

            with get_db() as connection:
                connection.execute(
                    """
                    UPDATE campaign_records
                    SET company_id = ?
                    WHERE id = ?
                    """,
                    (company_id, record_id),
                )

            linked_count += 1

        except Exception as error:
            failed_count += 1
            print(
                f"Could not link {brand_name}: {error}"
            )

    return {
        "campaign_id": campaign_id,
        "total_records": len(records),
        "linked_records": linked_count,
        "new_companies_created": created_count,
        "existing_companies_reused": existing_count,
        "failed_records": failed_count,
    }
