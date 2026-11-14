
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports" / "final"

PLAN_FILE = DATA / "lusha_prospecting_plan.csv"
TRAFFIC_FILE = DATA / "traffic_enrichment_results.csv"
CONTACTS_FILE = DATA / "lusha_discovered_contacts.csv"

OUTPUT_CSV = DATA / "lusha_company_priority.csv"
OUTPUT_EXCEL = REPORTS / "Quiklee_Lead_Prioritization.xlsx"


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

    return pd.read_csv(path, dtype=str).fillna("")


def normalize_domain(value):
    return (
        str(value)
        .lower()
        .strip()
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .rstrip("/")
    )


def main():

    plan = read_csv(PLAN_FILE)
    traffic = read_csv(TRAFFIC_FILE)
    contacts = read_csv(CONTACTS_FILE)

    required_plan = [
        "company_name",
        "company_domain",
        "role_category",
        "manual_review_required"
    ]

    required_traffic = [
        "domain",
        "monthly_visits",
        "status"
    ]

    for column in required_plan:
        if column not in plan.columns:
            raise ValueError(f"Missing plan column: {column}")

    for column in required_traffic:
        if column not in traffic.columns:
            raise ValueError(f"Missing traffic column: {column}")

    # Normalize domains for reliable joins.
    plan["domain_key"] = plan["company_domain"].apply(normalize_domain)
    traffic["domain_key"] = traffic["domain"].apply(normalize_domain)

    traffic["monthly_visits"] = pd.to_numeric(
        traffic["monthly_visits"],
        errors="coerce"
    )

    # Keep only completed traffic records with usable visitor values.
    valid_traffic = traffic[
        (traffic["status"].str.lower() == "completed") &
        (traffic["monthly_visits"] > 0)
    ].copy()

    # One traffic record per domain.
    valid_traffic = valid_traffic.drop_duplicates(
        subset=["domain_key"],
        keep="last"
    )

    # Build company-level prospecting summary.
    companies = (
        plan.groupby(
            ["company_name", "company_domain", "domain_key"],
            as_index=False
        )
        .agg(
            remaining_role_gaps=("role_category", "nunique"),
            planned_searches=("search_id", "count"),
            manual_review_required=("manual_review_required", "max")
        )
    )

    # Attach traffic information.
    companies = companies.merge(
        valid_traffic[
            ["domain_key", "monthly_visits", "reporting_month", "global_rank"]
        ],
        on="domain_key",
        how="left"
    )

    # Determine existing discovered contact coverage.
    discovered = set()

    if not contacts.empty:

        for _, contact in contacts.iterrows():

            domain = normalize_domain(
                contact.get("company_domain", "")
            )

            if domain:
                discovered.add(domain)

    companies["has_discovered_contact"] = companies[
        "domain_key"
    ].isin(discovered)

    # Estimate covered roles using known discovered contact titles.
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

    discovered_roles = set()

    for _, contact in contacts.iterrows():

        domain = normalize_domain(
            contact.get("company_domain", "")
        )

        role = infer_role(
            contact.get("job_title", ""),
            contact.get("discovery_source", "")
        )

        if domain and role:
            discovered_roles.add((domain, role))

    companies["discovered_role_count"] = companies.apply(
        lambda row: sum(
            1 for domain, role in discovered_roles
            if domain == row["domain_key"]
        ),
        axis=1
    )

    companies["data_quality_status"] = companies[
        "monthly_visits"
    ].apply(
        lambda value: "Verified traffic record"
        if pd.notna(value) else "Traffic data missing"
    )

    companies["manual_review_required"] = (
        companies["manual_review_required"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )

    # 1. Traffic score: percentile ranking, maximum 40 points.
    traffic_rank = companies["monthly_visits"].rank(
        pct=True,
        method="average"
    )

    companies["traffic_score"] = (
        traffic_rank.fillna(0) * 40
    ).round(2)

    # 2. Role-gap score: more outstanding roles mean greater prospecting need.
    max_gaps = max(
        companies["remaining_role_gaps"].max(),
        1
    )

    companies["role_gap_score"] = (
        companies["remaining_role_gaps"] / max_gaps * 40
    ).round(2)

    # 3. Data-quality score.
    companies["data_quality_score"] = companies.apply(
        lambda row: (
            20
            if row["data_quality_status"] == "Verified traffic record"
            and not row["manual_review_required"]
            else 10
            if row["data_quality_status"] == "Verified traffic record"
            else 0
        ),
        axis=1
    )

    companies["priority_score"] = (
        companies["traffic_score"]
        + companies["role_gap_score"]
        + companies["data_quality_score"]
    ).round(2)

    companies["priority_tier"] = pd.cut(
        companies["priority_score"],
        bins=[-1, 49.99, 69.99, 100],
        labels=["C", "B", "A"]
    ).astype(str)

    companies = companies.sort_values(
        by=["priority_score", "monthly_visits"],
        ascending=[False, False]
    ).reset_index(drop=True)

    companies.insert(
        0,
        "priority_rank",
        range(1, len(companies) + 1)
    )

    output_columns = [
        "priority_rank",
        "priority_tier",
        "company_name",
        "company_domain",
        "priority_score",
        "traffic_score",
        "role_gap_score",
        "data_quality_score",
        "monthly_visits",
        "remaining_role_gaps",
        "discovered_role_count",
        "has_discovered_contact",
        "planned_searches",
        "data_quality_status",
        "manual_review_required"
    ]

    result = companies[output_columns].copy()

    REPORTS.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    summary = (
        result.groupby("priority_tier", observed=False)
        .agg(
            companies=("company_name", "count"),
            average_score=("priority_score", "mean"),
            planned_searches=("planned_searches", "sum")
        )
        .reset_index()
    )

    with pd.ExcelWriter(
        OUTPUT_EXCEL,
        engine="openpyxl"
    ) as writer:

        result.to_excel(
            writer,
            sheet_name="Company Priorities",
            index=False
        )

        summary.to_excel(
            writer,
            sheet_name="Priority Summary",
            index=False
        )

        result[
            result["has_discovered_contact"]
        ].to_excel(
            writer,
            sheet_name="Existing Contacts",
            index=False
        )

        result[
            result["manual_review_required"]
        ].to_excel(
            writer,
            sheet_name="Manual Review",
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
                ].width = min(max(max_length + 2, 12), 40)

    print("\nQUIKLEE LEAD PRIORITIZATION")
    print("=" * 55)

    print("Companies ranked:", len(result))
    print(
        "Companies with discovered contacts:",
        int(result["has_discovered_contact"].sum())
    )

    print("\nPriority distribution:")
    print(summary.to_string(index=False))

    print("\nTOP 10 COMPANIES:")
    print(
        result[
            [
                "priority_rank",
                "company_name",
                "priority_tier",
                "priority_score",
                "monthly_visits",
                "remaining_role_gaps"
            ]
        ].head(10).to_string(index=False)
    )

    print("\nCSV:", OUTPUT_CSV)
    print("Excel:", OUTPUT_EXCEL)

    print("\nNo Lusha API requests were made.")
    print("No credits were consumed.")


if __name__ == "__main__":
    main()
