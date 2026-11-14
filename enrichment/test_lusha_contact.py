
import json
from pathlib import Path

from enrichment.lusha_integration import LushaClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent

OUTPUT_FILE = (
    PROJECT_ROOT / "data" / "lusha_search_results.json"
)


def main():

    client = LushaClient()

    contact = {
        "clientReferenceId": "quiklee-kushals-001",
        "firstName": "Ankit",
        "lastName": "Gulechha",
        "companyName": "Kushals",
        "companyDomain": "kushals.com"
    }

    try:
        print("\nSearching Lusha for one CRM contact...")

        response = client.search_contacts([contact])

        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            OUTPUT_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                response,
                file,
                indent=4,
                ensure_ascii=False
            )

        results = response.get("results", [])

        print("\nLUSHA SEARCH COMPLETED")
        print("=" * 50)

        print("Results returned:", len(results))
        print(
            "Credits charged:",
            response.get("billing", {}).get("creditsCharged", 0)
        )

        print("\nSaved API response to:")
        print(OUTPUT_FILE)

    except Exception as error:
        print("\nLUSHA API REQUEST FAILED")
        print(error)

    finally:
        client.close()


if __name__ == "__main__":
    main()
