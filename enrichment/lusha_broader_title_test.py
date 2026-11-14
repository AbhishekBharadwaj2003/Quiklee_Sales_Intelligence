
from pathlib import Path
import argparse
import json
from datetime import datetime, timezone

from enrichment.lusha_prospecting import LushaProspectingClient


ROOT = Path(__file__).resolve().parent.parent

OUTPUT_DIR = ROOT / "data" / "lusha_prospecting"
RAW_DIR = OUTPUT_DIR / "raw_responses"

COMPANY = "Bacca Bucci"
DOMAIN = "baccabucci.com"
SEARCH_ID = "BACCABUCCI-OPERATIONS-BROAD"

JOB_TITLES = [
    "Operations Manager",
    "Business Operations Manager",
    "General Manager",
    "Head of Business Operations"
]

SENIORITY_IDS = [9, 8, 6, 5]


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send the request to Lusha"
    )

    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        help="Confirm that the request may consume credits"
    )

    return parser.parse_args()


def build_payload():
    return {
        "filters": {
            "companies": {
                "include": {
                    "domains": [DOMAIN]
                }
            },
            "contacts": {
                "include": {
                    "jobTitles": JOB_TITLES,
                    "seniorityIds": SENIORITY_IDS
                }
            }
        },
        "pagination": {
            "page": 0,
            "size": 10
        },
        "options": {
            "includePartialProfiles": True,
            "excludeDnc": False,
            "maxContactsPerCompany": 2
        }
    }


def main():

    args = parse_args()

    if args.execute != args.confirm_paid:
        raise ValueError(
            "Live execution requires both --execute and --confirm-paid."
        )

    payload = build_payload()

    print("\nBACCABUCCI BROADER TITLE TEST")
    print("=" * 50)
    print("Company:", COMPANY)
    print("Domain:", DOMAIN)
    print("Search ID:", SEARCH_ID)
    print("Job titles:", ", ".join(JOB_TITLES))
    print("Maximum contacts:", 2)

    print("\nAPI payload:")
    print(json.dumps(payload, indent=4))

    if not args.execute:
        print("\nDRY RUN ONLY")
        print("No Lusha API request was made.")
        print("No credits were consumed.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("\nSending live request to Lusha...")

    with LushaProspectingClient() as client:
        response = client.prospect_contacts(payload)

    results = response.get("results", [])
    billing = response.get("billing", {})

    output = {
        "search_id": SEARCH_ID,
        "company": COMPANY,
        "domain": DOMAIN,
        "job_titles": JOB_TITLES,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "response": response
    }

    output_path = RAW_DIR / f"{SEARCH_ID}.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)

    print("\nSEARCH RESULTS")
    print("=" * 50)
    print("Contacts returned:", len(results))
    print("Credits charged:", billing.get("creditsCharged", 0))
    print("Request ID:", response.get("requestId", "Not provided"))
    print("Low balance:", billing.get("lowBalance", "Not provided"))
    print("Response saved:", output_path)

    for contact in results:
        name = " ".join(
            part for part in [
                contact.get("firstName", ""),
                contact.get("lastName", "")
            ] if part
        )

        job = contact.get("jobTitle", {})
        title = job.get("title", "") if isinstance(job, dict) else ""

        print(f"\n{name} | {title}")
        print("LinkedIn:", contact.get("socialLinks", {}).get("linkedin", ""))

    print("\nNo email or phone reveal was performed.")


if __name__ == "__main__":
    main()
