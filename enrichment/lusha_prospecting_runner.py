from pathlib import Path
import argparse
import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd
from enrichment.lusha_prospecting import LushaProspectingClient

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "quiklee_sales.db"
QUEUE_FILE = ROOT / "data" / "lusha_priority_search_queue.csv"
OUTPUT_DIR = ROOT / "data" / "lusha_prospecting"
HISTORY_FILE = OUTPUT_DIR / "search_history.csv"
RAW_DIR = OUTPUT_DIR / "raw_responses"
CONTACTS_CSV = ROOT / "data" / "lusha_discovered_contacts.csv"
CONTACTS_EXCEL = ROOT / "reports" / "final" / "Lusha_Discovered_Contacts.xlsx"

TRAFFIC_THRESHOLD = 100000
TRAFFIC_SOURCE = "TabAPI"
TRAFFIC_RESEARCH_TYPE = "traffic_analysis"
SENIORITY_IDS = [9, 8, 6, 5]

CONTACT_COLUMNS = [
    "lusha_contact_id", "first_name", "last_name", "full_name",
    "job_title", "departments", "seniority", "company_name",
    "company_domain", "company_id", "country", "state", "city",
    "linkedin_url", "email_reveal_available", "email_reveal_credits",
    "phone_reveal_available", "phone_reveal_credits",
    "discovery_source", "discovery_status",
]


def normalize_domain(value):
    domain = str(value or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.split("/")[0].split("?")[0].split("#")[0]
    return domain.removeprefix("www.").rstrip(".")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Quiklee Priority-Based Lusha Runner"
    )
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--search-id",
        type=str,
        default="",
        help="Run only this exact search ID (for example: LUSHA-003-R1).",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    return parser.parse_args()


def verify_traffic_eligibility(row):
    """SQLite TabAPI traffic record is the mandatory prospecting gate."""
    domain = normalize_domain(row.get("company_domain", ""))
    if not domain:
        return {"eligible": False, "reason": "Missing company domain."}
    if not DB_FILE.exists():
        return {"eligible": False, "reason": "SQLite database not found."}

    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    try:
        all_companies = connection.execute(
            """SELECT id, company_name, domain, website_url
               FROM companies
               WHERE domain IS NOT NULL OR website_url IS NOT NULL"""
        ).fetchall()
        matches = [
            company for company in all_companies
            if normalize_domain(company["domain"] or company["website_url"])
            == domain
        ]
        if len(matches) == 0:
            return {
                "eligible": False,
                "reason": f"No SQLite company record for {domain}.",
            }
        if len(matches) > 1:
            return {
                "eligible": False,
                "reason": f"Multiple SQLite company records match {domain}.",
            }

        company = matches[0]
        rows = connection.execute(
            """SELECT findings, researched_at, id
               FROM research_history
               WHERE company_id = ?
                 AND research_type = ?
                 AND source = ?
               ORDER BY researched_at DESC, id DESC""",
            (company["id"], TRAFFIC_RESEARCH_TYPE, TRAFFIC_SOURCE),
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        return {
            "eligible": False,
            "reason": f"No TabAPI traffic record for {domain}.",
        }

    parsed = []
    for item in rows:
        try:
            findings = json.loads(item["findings"] or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(findings, dict) and findings.get("reporting_month"):
            parsed.append((str(findings["reporting_month"]), findings))

    if not parsed:
        return {
            "eligible": False,
            "reason": f"Traffic findings are invalid for {domain}.",
        }

    latest_month = max(month for month, _ in parsed)
    latest = [f for month, f in parsed if month == latest_month]
    try:
        visits_set = {int(f.get("monthly_visits") or 0) for f in latest}
    except (TypeError, ValueError):
        return {
            "eligible": False,
            "reason": f"Invalid visitor count in SQLite for {domain}.",
        }
    statuses = {str(f.get("status") or "").lower() for f in latest}

    if len(visits_set) != 1 or len(statuses) != 1:
        return {
            "eligible": False,
            "reason": f"Conflicting latest traffic records for {domain}.",
        }

    visits = next(iter(visits_set))
    status = next(iter(statuses))
    if status != "completed":
        return {
            "eligible": False,
            "reason": f"Latest TabAPI status is '{status}' for {domain}.",
        }
    if visits < TRAFFIC_THRESHOLD:
        return {
            "eligible": False,
            "reason": (
                f"{domain} has {visits:,} visitors; "
                f"{TRAFFIC_THRESHOLD:,} required."
            ),
        }

    queued_visits = str(row.get("monthly_visits", "")).strip()
    if queued_visits:
        try:
            queued_visits = int(
                float(queued_visits.replace(",", ""))
            )
        except ValueError:
            return {
                "eligible": False,
                "reason": f"Invalid queue traffic value for {domain}.",
            }
        if queued_visits != visits:
            return {
                "eligible": False,
                "reason": (
                    f"Queue/SQLite traffic mismatch for {domain}: "
                    f"{queued_visits:,} vs {visits:,}."
                ),
            }

    return {
        "eligible": True,
        "company_id": company["id"],
        "company_name": company["company_name"],
        "domain": domain,
        "monthly_visits": visits,
        "reporting_month": latest_month,
        "source": TRAFFIC_SOURCE,
    }


def build_payload(row):
    titles = [
        title.strip()
        for title in str(row["verified_job_titles"]).split("|")
        if title.strip()
    ]
    domain = normalize_domain(row["company_domain"])
    if not domain:
        raise ValueError(f"Missing company domain for {row['company_name']}")
    if not titles:
        raise ValueError(
            f"No verified job titles configured for {row['company_name']}"
        )
    return {
        "filters": {
            "companies": {"include": {"domains": [domain]}},
            "contacts": {
                "include": {
                    "jobTitles": titles,
                    "seniorityIds": SENIORITY_IDS,
                }
            },
        },
        "pagination": {"page": 0, "size": 10},
        "options": {
            "includePartialProfiles": True,
            "excludeDnc": False,
            "maxContactsPerCompany": 2,
        },
    }


def load_history():
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(HISTORY_FILE, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def save_history(history):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    history.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")


def append_history(history, record):
    updated = pd.concat([history, pd.DataFrame([record])], ignore_index=True)
    save_history(updated)
    return updated


def save_raw_response(search_id, response):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{search_id}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(response, file, indent=4, ensure_ascii=False)
    return path


def make_history_record(
    row, status, contacts=0, credits="", request_id="", error="",
    integration_status="not_attempted", contacts_added=0,
):
    return {
        "search_id": row["search_id"],
        "execution_order": row.get("execution_order", ""),
        "company_name": row["company_name"],
        "company_domain": row["company_domain"],
        "role_category": row["role_category"],
        "priority_tier": row.get("priority_tier", ""),
        "priority_score": row.get("priority_score", ""),
        "status": status,
        "contacts_returned": contacts,
        "contacts_added": contacts_added,
        "credits_charged": credits,
        "request_id": request_id,
        "integration_status": integration_status,
        "error": error,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def extract_contact(contact, search_id, role_category):
    job = contact.get("jobTitle") or {}
    company = contact.get("company") or {}
    location = contact.get("location") or {}
    social = contact.get("socialLinks") or {}
    reveal = {
        item.get("field"): item
        for item in contact.get("canReveal", [])
        if isinstance(item, dict)
    }
    first = contact.get("firstName", "") or ""
    last = contact.get("lastName", "") or ""
    emails = reveal.get("emails", {})
    phones = reveal.get("phones", {})
    return {
        "lusha_contact_id": contact.get("id", "") or "",
        "first_name": first,
        "last_name": last,
        "full_name": " ".join(x for x in (first, last) if x),
        "job_title": job.get("title", ""),
        "departments": " | ".join(job.get("departments", [])),
        "seniority": job.get("seniority", ""),
        "company_name": company.get("name", ""),
        "company_domain": company.get("domain", ""),
        "company_id": company.get("id", ""),
        "country": location.get("country", ""),
        "state": location.get("state", ""),
        "city": location.get("city", ""),
        "linkedin_url": social.get("linkedin", ""),
        "email_reveal_available": emails.get("availability", "") == "available",
        "email_reveal_credits": emails.get("credits", 0),
        "phone_reveal_available": phones.get("availability", "") == "available",
        "phone_reveal_credits": phones.get("credits", 0),
        "discovery_source": f"lusha_priority_runner:{search_id}:{role_category}",
        "discovery_status": "discovered_not_revealed",
    }


def load_existing_contacts():
    if not CONTACTS_CSV.exists():
        return pd.DataFrame(columns=CONTACT_COLUMNS)
    try:
        existing = pd.read_csv(CONTACTS_CSV, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        existing = pd.DataFrame(columns=CONTACT_COLUMNS)
    for column in CONTACT_COLUMNS:
        if column not in existing.columns:
            existing[column] = ""
    return existing


def integrate_contacts(results, search_id, role_category):
    existing = load_existing_contacts()
    new_rows = []
    for contact in results:
        if not isinstance(contact, dict):
            continue
        record = extract_contact(contact, search_id, role_category)
        if record["lusha_contact_id"]:
            new_rows.append(record)

    if not new_rows:
        return 0, len(existing)

    new_records = pd.DataFrame(new_rows, columns=CONTACT_COLUMNS)
    existing_ids = set(existing["lusha_contact_id"].astype(str))
    new_records = new_records[
        ~new_records["lusha_contact_id"].astype(str).isin(existing_ids)
    ]
    updated = pd.concat([existing, new_records], ignore_index=True)
    updated = updated.drop_duplicates(
        subset=["lusha_contact_id"], keep="first"
    )

    CONTACTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_EXCEL.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(CONTACTS_CSV, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(CONTACTS_EXCEL, engine="openpyxl") as writer:
        updated.to_excel(
            writer, sheet_name="Discovered Contacts", index=False
        )
    return len(new_records), len(updated)


def main():
    args = parse_arguments()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    if args.execute != args.confirm_paid:
        raise ValueError(
            "Live execution requires BOTH --execute and --confirm-paid."
        )
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(
            f"Priority queue not found: {QUEUE_FILE}. "
            "Run the priority queue builder first."
        )

    queue = pd.read_csv(QUEUE_FILE, dtype=str).fillna("")
    if queue.empty:
        print("Priority search queue is empty.")
        return

    required = [
        "execution_order", "search_id", "company_name", "company_domain",
        "role_category", "verified_job_titles", "priority_tier",
        "priority_score",
    ]
    missing = [column for column in required if column not in queue.columns]
    if missing:
        raise ValueError(f"Missing priority queue columns: {missing}")

    queue["execution_order"] = pd.to_numeric(
        queue["execution_order"], errors="coerce"
    )
    queue = queue.sort_values("execution_order")
    history = load_history()
    attempted = set()
    if not history.empty and "search_id" in history.columns:
        attempted = set(history["search_id"].astype(str).str.strip())

    if args.search_id:
        requested_id = args.search_id.strip()
        matches = queue[
            queue["search_id"].astype(str).str.strip() == requested_id
        ]
        if len(matches) == 0:
            raise ValueError(
                f"Search ID '{requested_id}' was not found in the priority queue."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Search ID '{requested_id}' appears more than once in the priority queue."
            )
        if requested_id in attempted:
            raise ValueError(
                f"Search ID '{requested_id}' is already present in search history. "
                "The runner will not repeat an attempted search."
            )
        pending = matches
    else:
        pending = queue[
            ~queue["search_id"].astype(str).str.strip().isin(attempted)
        ].head(args.limit)

    print("\nQUIKLEE PRIORITY LUSHA RUNNER")
    print("=" * 55)
    print("Mode:", "LIVE API" if args.execute else "DRY RUN")
    print("Traffic authority: SQLite TabAPI records")
    print("Minimum visitors:", f"{TRAFFIC_THRESHOLD:,}")
    print("Total searches:", len(queue))
    print("Previously attempted:", len(attempted))
    if args.search_id:
        print("Target search ID:", args.search_id.strip())
    print("Pending:", len(pending))

    if pending.empty:
        print("No new searches are pending.")
        return

    eligible = []
    blocked = 0
    for _, row in pending.iterrows():
        check = verify_traffic_eligibility(row)
        print(f"\n{row['company_name']} | {row['company_domain']}")
        if not check["eligible"]:
            blocked += 1
            print("TRAFFIC GATE: BLOCKED -", check["reason"])
            continue
        print("TRAFFIC GATE: PASSED")
        print("SQLite company ID:", check["company_id"])
        print("Monthly visitors:", f"{check['monthly_visits']:,}")
        print("Reporting month:", check["reporting_month"])
        eligible.append((row, check))

    print("\nTRAFFIC GATE SUMMARY")
    print("Eligible:", len(eligible))
    print("Blocked:", blocked)

    if not eligible:
        print("No eligible searches. No Lusha requests were made.")
        return

    if not args.execute:
        for row, check in eligible:
            print("\nPrepared search:", row["search_id"])
            print("Company:", row["company_name"])
            print("Role:", row["role_category"])
            print(
                "SQLite-verified traffic:",
                f"{check['monthly_visits']:,}",
                check["reporting_month"],
            )
            print(json.dumps(build_payload(row), indent=4))
        print("\nDRY RUN COMPLETED")
        print("No Lusha API requests were made.")
        print("No Lusha credits were consumed.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_contacts = total_new = total_credits = 0

    with LushaProspectingClient() as client:
        for row, _ in eligible:
            search_id = str(row["search_id"])
            print(f"\nExecuting {search_id}: {row['company_name']}")

            try:
                # Mandatory second check immediately before paid API call.
                final_check = verify_traffic_eligibility(row)
                if not final_check["eligible"]:
                    print("FINAL TRAFFIC CHECK: BLOCKED")
                    print(final_check["reason"])
                    continue

                payload = build_payload(row)
                response = client.prospect_contacts(payload)
                if not isinstance(response, dict):
                    raise RuntimeError("Unexpected response format from Lusha.")

                raw_path = save_raw_response(search_id, response)
                print("Raw response saved:", raw_path)

                if "billing" not in response:
                    history = append_history(
                        history,
                        make_history_record(
                            row, "billing_unconfirmed",
                            error="API response did not contain billing information.",
                        ),
                    )
                    print("Billing information missing; stopping safely.")
                    break

                results = response.get("results", [])
                if not isinstance(results, list):
                    raise RuntimeError("Lusha results field was not a list.")

                billing = response["billing"]
                credits = int(billing.get("creditsCharged", 0) or 0)
                returned = len(results)
                integration_status = "completed"
                integration_error = ""
                added = unique_total = 0

                try:
                    added, unique_total = integrate_contacts(
                        results, search_id, row["role_category"]
                    )
                except Exception as exc:
                    integration_status = "failed"
                    integration_error = str(exc)

                history = append_history(
                    history,
                    make_history_record(
                        row,
                        "completed",
                        returned,
                        credits,
                        response.get("requestId", ""),
                        error=integration_error,
                        integration_status=integration_status,
                        contacts_added=added,
                    ),
                )

                total_contacts += returned
                total_new += added
                total_credits += credits
                print("Contacts returned:", returned)
                print("New contacts added:", added)
                print("Total unique contacts:", unique_total)
                print("Credits charged:", credits)
                print("Contact integration:", integration_status)

                if integration_status == "failed":
                    print("Integration error:", integration_error)
                    print("Raw response preserved for manual recovery.")

                if billing.get("lowBalance", False):
                    print("Lusha reported low balance; stopping.")
                    break

            except Exception as exc:
                history = append_history(
                    history,
                    make_history_record(row, "failed", error=str(exc)),
                )
                print("Search failed:", exc)
                print("Stopping execution; this search will not auto-retry.")
                break

    print("\nRUN SUMMARY")
    print("=" * 55)
    print("Contacts returned:", total_contacts)
    print("New contacts integrated:", total_new)
    print("Credits charged:", total_credits)
    print("Search history:", HISTORY_FILE)
    print("Raw responses:", RAW_DIR)
    print("Contacts CSV:", CONTACTS_CSV)
    print("Contacts Excel:", CONTACTS_EXCEL)
    print("Execution completed.")


if __name__ == "__main__":
    main()
