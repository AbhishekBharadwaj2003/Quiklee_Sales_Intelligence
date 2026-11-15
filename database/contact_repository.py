
from database.db import get_db


def add_contact(company_id: int, contact: dict):
    """Save a contact if it does not already exist."""

    name = contact.get("contact_name", "").strip()
    email = contact.get("email", "").strip().lower()
    linkedin = contact.get("linkedin_url", "").strip()

    if not name and not email and not linkedin:
        raise ValueError(
            "At least a name, email or LinkedIn URL is required."
        )

    with get_db() as connection:

        # Check for an existing contact
        designation = (contact.get("designation") or "").strip()

        existing = connection.execute(
            """
            SELECT id FROM company_contacts
            WHERE company_id = ?
            AND (
                (? != '' AND LOWER(email) = ?)
                OR (? != '' AND linkedin_url = ?)
                OR (
                    ? = ''
                    AND ? = ''
                    AND LOWER(contact_name) = LOWER(?)
                    AND LOWER(COALESCE(designation, '')) = LOWER(?)
                )
            )
            LIMIT 1
            """,
            (
                company_id,
                email, email,
                linkedin, linkedin,
                email, linkedin,
                name, designation
            )
        ).fetchone()

        if existing:
            return {
                "success": False,
                "message": "Contact already exists.",
                "contact_id": existing["id"]
            }

        cursor = connection.execute(
            """
            INSERT INTO company_contacts (
                company_id,
                contact_name,
                designation,
                email,
                phone,
                linkedin_url,
                contact_source,
                enrichment_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                name,
                contact.get("designation"),
                email or None,
                contact.get("phone"),
                linkedin or None,
                contact.get("contact_source"),
                contact.get("enrichment_status", "manual")
            )
        )

        return {
            "success": True,
            "message": "Contact saved successfully.",
            "contact_id": cursor.lastrowid
        }


def get_company_contacts(company_id: int):
    """Retrieve all contacts belonging to a company."""

    with get_db() as connection:

        records = connection.execute(
            """
            SELECT *
            FROM company_contacts
            WHERE company_id = ?
            ORDER BY created_at DESC
            """,
            (company_id,)
        ).fetchall()

        return [dict(record) for record in records]


def update_contact(contact_id: int, updates: dict):
    """Update existing contact information."""

    allowed_fields = {
        "contact_name",
        "designation",
        "email",
        "phone",
        "linkedin_url",
        "contact_source",
        "enrichment_status"
    }

    updates = {
        key: value
        for key, value in updates.items()
        if key in allowed_fields
    }

    if not updates:
        return False

    fields = ", ".join(
        f"{field} = ?" for field in updates
    )

    values = list(updates.values())
    values.append(contact_id)

    with get_db() as connection:

        cursor = connection.execute(
            f"""
            UPDATE company_contacts
            SET {fields}
            WHERE id = ?
            """,
            values
        )

        return cursor.rowcount > 0


def contact_exists(company_id: int, email=None, linkedin_url=None):
    """Check whether a contact already exists."""

    email = (email or "").strip().lower()
    linkedin_url = (linkedin_url or "").strip()

    if not email and not linkedin_url:
        return False

    with get_db() as connection:

        result = connection.execute(
            """
            SELECT id
            FROM company_contacts
            WHERE company_id = ?
            AND (
                (? != '' AND LOWER(email) = ?)
                OR (? != '' AND linkedin_url = ?)
            )
            LIMIT 1
            """,
            (
                company_id,
                email, email,
                linkedin_url, linkedin_url
            )
        ).fetchone()

        return result is not None


if __name__ == "__main__":

    from database.company_repository import get_all_companies

    companies = get_all_companies()

    if not companies:
        print("No companies found.")
        raise SystemExit

    company = companies[0]

    print("\nQUIKLEE CONTACT REPOSITORY TEST")
    print("=" * 50)

    result = add_contact(
        company["id"],
        {
            "contact_name": "Test Contact",
            "designation": "Business Development",
            "email": "test@example.com",
            "linkedin_url": "https://linkedin.com/in/test-contact",
            "contact_source": "Manual Test"
        }
    )

    print("\nInsert result:", result)

    contacts = get_company_contacts(company["id"])

    print("\nSaved contacts:")

    for contact in contacts:
        print(contact)
