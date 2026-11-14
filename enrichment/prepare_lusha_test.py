
import json
from pathlib import Path

from enrichment.lusha_prospecting import LushaProspectingClient


payload = {
    "pagination": {
        "page": 0,
        "size": 10
    },
    "filters": {
        "contacts": {
            "include": {
                "jobTitles": [
                    "Head of Growth"
                ],
                "seniority": [
                    9,
                    8,
                    6,
                    5
                ]
            }
        },
        "companies": {
            "include": {
                "domains": [
                    "duroflexworld.com"
                ]
            }
        }
    },
    "options": {
        "includePartialProfiles": True,
        "excludeDnc": True,
        "maxContactsPerCompany": 5
    }
}


def main():
    print("Submitting Duroflex Growth Head test to Lusha...")
    print("Company domain: duroflexworld.com")
    print("Target: Head of Growth")
    print("Maximum results: 10")
    print("-" * 45)

    # Exactly one API request. No automatic retries.
    with LushaProspectingClient() as client:
        response = client.prospect_contacts(payload)

    output_path = Path("data/lusha_duroflex_growth_test.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(response, file, indent=4, ensure_ascii=False)

    print("\nRequest completed successfully.")
    print(f"Full response saved to: {output_path}")

    if isinstance(response, dict):
        print("\nResponse summary:")
        print("Response fields:", list(response.keys()))

        for key in ("resultsReturned", "creditsCharged", "lowBalance"):
            if key in response:
                print(f"{key}: {response[key]}")


if __name__ == "__main__":
    main()
