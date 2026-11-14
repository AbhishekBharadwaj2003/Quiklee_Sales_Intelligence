
import tempfile
from pathlib import Path

import pandas as pd

from enrichment import lusha_prospecting_runner as runner


def main():
    original_csv = runner.CONTACTS_CSV
    original_excel = runner.CONTACTS_EXCEL

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)

            runner.CONTACTS_CSV = temp / "contacts.csv"
            runner.CONTACTS_EXCEL = temp / "contacts.xlsx"

            simulated_results = [
                {
                    "id": "TEST-LUSHA-001",
                    "firstName": "Test",
                    "lastName": "Contact One",
                    "jobTitle": {
                        "title": "Head of Operations",
                        "departments": ["Operations"],
                        "seniority": "Head",
                    },
                    "company": {
                        "name": "Test Brand",
                        "domain": "testbrand.com",
                        "id": "TEST-COMPANY-001",
                    },
                    "location": {
                        "country": "India",
                        "state": "Karnataka",
                        "city": "Bengaluru",
                    },
                    "socialLinks": {
                        "linkedin": "https://linkedin.com/in/test-contact-one"
                    },
                    "canReveal": [
                        {
                            "field": "emails",
                            "availability": "available",
                            "credits": 1,
                        },
                        {
                            "field": "phones",
                            "availability": "available",
                            "credits": 5,
                        },
                    ],
                },
                {
                    "id": "TEST-LUSHA-002",
                    "firstName": "Test",
                    "lastName": "Contact Two",
                    "jobTitle": {
                        "title": "Operations Manager",
                        "departments": ["Operations"],
                        "seniority": "Manager",
                    },
                    "company": {
                        "name": "Test Brand",
                        "domain": "testbrand.com",
                        "id": "TEST-COMPANY-001",
                    },
                    "location": {
                        "country": "India",
                        "state": "Karnataka",
                        "city": "Bengaluru",
                    },
                    "socialLinks": {},
                    "canReveal": [],
                },
            ]

            print("\nTEST 1: Integrating two simulated contacts")

            added, total = runner.integrate_contacts(
                simulated_results,
                "TEST-SEARCH-001",
                "operations_head",
            )

            print("New contacts:", added)
            print("Total contacts:", total)

            assert added == 2
            assert total == 2

            print("\nTEST 2: Checking duplicate protection")

            added_again, total_again = runner.integrate_contacts(
                simulated_results,
                "TEST-SEARCH-002",
                "operations_head",
            )

            print("New contacts:", added_again)
            print("Total contacts:", total_again)

            assert added_again == 0
            assert total_again == 2

            print("\nTEST 3: Checking CSV and Excel files")

            assert runner.CONTACTS_CSV.exists()
            assert runner.CONTACTS_EXCEL.exists()

            df = pd.read_csv(runner.CONTACTS_CSV, dtype=str).fillna("")

            assert len(df) == 2
            assert df["lusha_contact_id"].nunique() == 2

            assert (
                df["discovery_status"] == "discovered_not_revealed"
            ).all()

            print("CSV created:", runner.CONTACTS_CSV.exists())
            print("Excel created:", runner.CONTACTS_EXCEL.exists())
            print("Unique IDs:", df["lusha_contact_id"].nunique())
            print("Reveal status: Not revealed")

            print("\nALL INTEGRATION TESTS PASSED")

    finally:
        runner.CONTACTS_CSV = original_csv
        runner.CONTACTS_EXCEL = original_excel


if __name__ == "__main__":
    main()
