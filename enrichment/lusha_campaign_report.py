
from pathlib import Path
import json
import re

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FINAL = ROOT / "reports" / "final"

PLAN_FILE = DATA / "lusha_prospecting_plan.csv"
CONTACTS_FILE = DATA / "lusha_discovered_contacts.csv"
HISTORY_FILE = DATA / "lusha_prospecting" / "search_history.csv"
FALLBACK_FILE = DATA / "lusha_fallback_search_queue.csv"

OUTPUT_FILE = FINAL / "Lusha_Campaign_Dashboard.xlsx"


def read_csv(path):
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def normalize(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def infer_role(title, source=""):

    title = str(title).lower()
    source = str(source).lower()

    if "growth" in title:
        return "Growth Head"

    if "operation" in title:
        return "Operations Head"

    if "supply chain" in title:
        return "Supply Chain Head"

    if any(term in title for term in [
        "marketplace", "e-commerce", "e commerce", "d2c"
    ]):
        return "Marketplace / E-commerce"

    if "general manager" in title and "broader_title_test" in source:
        return "Operations Head"

    return None


def load_json_response(path):

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Some files contain a wrapper around the API response.
        if isinstance(data, dict) and isinstance(data.get("response"), dict):
            data = data["response"]

        if not isinstance(data, dict):
            return None

        if "billing" not in data:
            return None

        return data

    except (OSError, json.JSONDecodeError):
        return None


def collect_billing():

    response_files = []

    raw_dir = DATA / "lusha_prospecting" / "raw_responses"

    if raw_dir.exists():
        response_files.extend(raw_dir.glob("*.json"))

    duroflex_file = DATA / "lusha_duroflex_growth_test.json"

    if duroflex_file.exists():
        response_files.append(duroflex_file)

    transactions = []
    seen_request_ids = set()

    for path in response_files:

        response = load_json_response(path)

        if not response:
            continue

        request_id = response.get("requestId", "")

        if not request_id or request_id in seen_request_ids:
            continue

        seen_request_ids.add(request_id)

        billing = response.get("billing", {})

        transactions.append({
            "request_id": request_id,
            "source_file": path.name,
            "results_returned": billing.get("resultsReturned", 0),
            "credits_charged": billing.get("creditsCharged", 0),
            "low_balance": billing.get("lowBalance", "")
        })

    return pd.DataFrame(transactions)


def build_contact_report(contacts):

    columns = [
        "lusha_contact_id",
        "full_name",
        "job_title",
        "company_name",
        "company_domain",
        "seniority",
        "country",
        "state",
        "city",
        "linkedin_url",
        "email_reveal_available",
        "email_reveal_credits",
        "phone_reveal_available",
        "phone_reveal_credits",
        "discovery_source",
        "discovery_status",
        "role_category"
    ]

    if contacts.empty:
        return pd.DataFrame(columns=columns)

    result = contacts.copy()

    for column in columns:
        if column not in result.columns:
            result[column] = ""

    result["role_category"] = result.apply(
        lambda row: infer_role(
            row.get("job_title", ""),
            row.get("discovery_source", "")
        ) or "Unclassified",
        axis=1
    )

    return result[columns]


def build_company_coverage(plan, contacts):

    if plan.empty:
        return pd.DataFrame()

    result = plan[
        ["company_name", "company_domain", "role_category"]
    ].drop_duplicates().copy()

    discovered = set()

    for _, contact in contacts.iterrows():

        role = infer_role(
            contact.get("job_title", ""),
            contact.get("discovery_source", "")
        )

        if not role:
            continue

        domain = normalize(contact.get("company_domain", ""))
        company = normalize(contact.get("company_name", ""))

        key = domain if domain else company

        discovered.add((key, role))

    result["discovery_status"] = result.apply(
        lambda row: (
            "Prospect discovered"
            if (
                normalize(row["company_domain"])
                or normalize(row["company_name"]),
                row["role_category"]
            ) in discovered
            else "Search planned"
        ),
        axis=1
    )

    return result.sort_values(
        ["company_name", "role_category"]
    ).reset_index(drop=True)


def build_role_summary(coverage):

    if coverage.empty:
        return pd.DataFrame()

    return (
        coverage.groupby("role_category")
        .agg(
            total_company_roles=("company_name", "count"),
            discovered=("discovery_status", lambda x: (x == "Prospect discovered").sum()),
            search_planned=("discovery_status", lambda x: (x == "Search planned").sum())
        )
        .reset_index()
    )


def main():

    plan = read_csv(PLAN_FILE)
    contacts = read_csv(CONTACTS_FILE)
    history = read_csv(HISTORY_FILE)
    fallback = read_csv(FALLBACK_FILE)

    if plan.empty:
        raise FileNotFoundError(
            "Prospecting plan is missing or empty. Run the planner first."
        )

    contact_report = build_contact_report(contacts)
    coverage = build_company_coverage(plan, contacts)
    role_summary = build_role_summary(coverage)
    billing = collect_billing()

    if not history.empty:

        if "processed_at" in history.columns:
            history = history.sort_values("processed_at")

        latest_history = history.drop_duplicates(
            subset=["search_id"],
            keep="last"
        )
    else:
        latest_history = history

    if not latest_history.empty:

        history_summary = (
            latest_history.groupby("status")
            .size()
            .reset_index(name="search_count")
        )

    else:
        history_summary = pd.DataFrame(
            columns=["status", "search_count"]
        )

    total_searches = len(plan)

    completed_searches = (
        len(latest_history[
            latest_history["status"] == "completed"
        ])
        if not latest_history.empty else 0
    )

    failed_searches = (
        len(latest_history[
            latest_history["status"] == "failed"
        ])
        if not latest_history.empty else 0
    )

    total_contacts = (
        contacts["lusha_contact_id"].nunique()
        if not contacts.empty and "lusha_contact_id" in contacts.columns
        else 0
    )

    total_credits = (
        pd.to_numeric(
            billing["credits_charged"],
            errors="coerce"
        ).fillna(0).sum()
        if not billing.empty else 0
    )

    total_api_results = (
        pd.to_numeric(
            billing["results_returned"],
            errors="coerce"
        ).fillna(0).sum()
        if not billing.empty else 0
    )

    verification_contacts = (
        contact_report[
            contact_report["role_category"] == "Operations Head"
        ].copy()
        if not contact_report.empty else pd.DataFrame()
    )

    if not verification_contacts.empty:
        verification_contacts = verification_contacts[
            verification_contacts["job_title"].str.contains(
                "general manager",
                case=False,
                na=False
            )
        ]

    overview = pd.DataFrame([
        ["Qualified companies", 23],
        ["Remaining planned searches", total_searches],
        ["Completed searches in history", completed_searches],
        ["Failed searches in history", failed_searches],
        ["Unique discovered contacts", total_contacts],
        ["Unique API requests with billing records", len(billing)],
        ["Contacts returned by recorded API transactions", total_api_results],
        ["Confirmed credits charged", total_credits],
        ["Fallback searches awaiting approval", len(fallback)],
        ["Contacts requiring role verification", len(verification_contacts)]
    ], columns=["Metric", "Value"])

    FINAL.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:

        overview.to_excel(
            writer,
            sheet_name="Campaign Overview",
            index=False
        )

        plan.to_excel(
            writer,
            sheet_name="Prospecting Plan",
            index=False
        )

        contact_report.to_excel(
            writer,
            sheet_name="Discovered Contacts",
            index=False
        )

        coverage.to_excel(
            writer,
            sheet_name="Company Role Coverage",
            index=False
        )

        role_summary.to_excel(
            writer,
            sheet_name="Role Summary",
            index=False
        )

        latest_history.to_excel(
            writer,
            sheet_name="Search History",
            index=False
        )

        billing.to_excel(
            writer,
            sheet_name="Credit Transactions",
            index=False
        )

        fallback.to_excel(
            writer,
            sheet_name="Fallback Queue",
            index=False
        )

        verification_contacts.to_excel(
            writer,
            sheet_name="Verification Required",
            index=False
        )

        history_summary.to_excel(
            writer,
            sheet_name="Execution Summary",
            index=False
        )

        for worksheet in writer.book.worksheets:

            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

            for column_cells in worksheet.columns:

                max_length = max(
                    len(str(cell.value or ""))
                    for cell in column_cells
                )

                worksheet.column_dimensions[
                    column_cells[0].column_letter
                ].width = min(max(max_length + 2, 12), 45)

    print("\nQUIKLEE LUSHA CAMPAIGN DASHBOARD")
    print("=" * 55)

    print("Planned searches:", total_searches)
    print("Completed searches:", completed_searches)
    print("Failed searches:", failed_searches)
    print("Unique contacts:", total_contacts)
    print("Recorded API transactions:", len(billing))
    print("API results returned:", total_api_results)
    print("Confirmed credits charged:", total_credits)
    print("Fallback searches awaiting approval:", len(fallback))

    print("\nDashboard generated:")
    print(OUTPUT_FILE)

    print("\nNo Lusha API requests were made.")
    print("No credits were consumed.")


if __name__ == "__main__":
    main()
