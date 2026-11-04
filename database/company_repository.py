
from database.db import get_db
from discovery.deduplication import normalize_domain, normalize_company_name


def add_company(company: dict):
    """Add a company unless its domain or normalized name already exists."""

    name = company.get("company_name") or company.get(
        "company_name_candidate"
    )

    website = company.get("website_url", "").strip()
    domain = normalize_domain(website) if website else ""

    if not name:
        raise ValueError("Company name is required.")

    with get_db() as connection:

        # Check domain first
        if domain:
            existing = connection.execute(
                "SELECT * FROM companies WHERE domain = ?",
                (domain,)
            ).fetchone()

            if existing:
                return {
                    "success": False,
                    "message": "Company already exists.",
                    "company_id": existing["id"]
                }

        # Check normalized company name
        existing_companies = connection.execute(
            "SELECT id, company_name FROM companies"
        ).fetchall()

        normalized_name = normalize_company_name(name)

        for existing in existing_companies:

            if normalize_company_name(
                existing["company_name"]
            ) == normalized_name:

                return {
                    "success": False,
                    "message": "Company name already exists.",
                    "company_id": existing["id"]
                }

        cursor = connection.execute(
            """
            INSERT INTO companies (
                company_name,
                website_url,
                domain,
                category,
                description,
                headquarters,
                linkedin_url,
                validation_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                website,
                domain,
                company.get("category"),
                company.get("description"),
                company.get("headquarters"),
                company.get("linkedin_url"),
                company.get("validation_status", "pending")
            )
        )

        return {
            "success": True,
            "message": "Company added successfully.",
            "company_id": cursor.lastrowid
        }


def get_company_by_id(company_id: int):
    """Retrieve a company using its database ID."""

    with get_db() as connection:

        result = connection.execute(
            "SELECT * FROM companies WHERE id = ?",
            (company_id,)
        ).fetchone()

        return dict(result) if result else None


def get_company_by_domain(domain: str):
    """Retrieve a company using its registered domain."""

    normalized_domain = normalize_domain(domain)

    if not normalized_domain:
        return None

    with get_db() as connection:

        result = connection.execute(
            "SELECT * FROM companies WHERE domain = ?",
            (normalized_domain,)
        ).fetchone()

        return dict(result) if result else None


def get_all_companies():
    """Retrieve all company records."""

    with get_db() as connection:

        results = connection.execute(
            "SELECT * FROM companies ORDER BY created_at DESC"
        ).fetchall()

        return [dict(row) for row in results]


def update_company(company_id: int, updates: dict):
    """Update selected company fields."""

    allowed_fields = {
        "company_name",
        "website_url",
        "domain",
        "category",
        "description",
        "headquarters",
        "linkedin_url",
        "company_size",
        "validation_status",
        "qualification_score",
        "qualification_category",
        "data_completeness",
        "research_status",
        "enrichment_status",
        "last_researched_at"
    }

    updates = {
        key: value
        for key, value in updates.items()
        if key in allowed_fields
    }

    if not updates:
        return False

    if "website_url" in updates:
        updates["domain"] = normalize_domain(
            updates["website_url"]
        )

    fields = ", ".join(
        f"{field} = ?" for field in updates
    )

    values = list(updates.values())

    values.append(company_id)

    with get_db() as connection:

        cursor = connection.execute(
            f"""
            UPDATE companies
            SET {fields}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            values
        )

        return cursor.rowcount > 0


def mark_company_researched(company_id: int):
    """Update the company's research status and timestamp."""

    return update_company(
        company_id,
        {
            "research_status": "completed",
            "last_researched_at": __import__(
                "datetime"
            ).datetime.now().isoformat()
        }
    )


if __name__ == "__main__":

    print("\nQUIKLEE COMPANY REPOSITORY TEST")
    print("=" * 50)

    sample_company = {
        "company_name": "Test Quiklee Brand",
        "website_url": "https://testquikleebrand.in/",
        "category": "Fashion and Apparel",
        "description": "Sample company for database testing.",
        "headquarters": "India",
        "validation_status": "pending"
    }

    result = add_company(sample_company)

    print("\nInsert result:")
    print(result)

    company_id = result.get("company_id")

    if company_id:

        company = get_company_by_id(company_id)

        print("\nRetrieved company:")
        print(company)

    print("\nTotal companies:", len(get_all_companies()))
