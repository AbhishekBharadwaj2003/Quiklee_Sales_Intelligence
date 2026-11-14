from pathlib import Path
import re

import pandas as pd

from database.company_repository import get_company_by_domain


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports" / "final"

PLAN = DATA / "lusha_prospecting_plan.csv"
PRIORITY = DATA / "lusha_company_priority.csv"

OUTPUT_CSV = DATA / "lusha_priority_search_queue.csv"
OUTPUT_EXCEL = REPORTS / "Lusha_Priority_Search_Queue.xlsx"
EXCLUDED_CSV = DATA / "lusha_priority_search_excluded.csv"

MINIMUM_MONTHLY_VISITS = 100_000


def parse_monthly_visits(value):
    """Parse visitor counts such as 100000, '100,000', '150K' or '1.2M'."""

    if value is None or pd.isna(value):
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    text = text.replace(",", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", text)

    if not match:
        return None

    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
    return int(number * multiplier)


def load_inputs():
    if not PLAN.exists():
        raise FileNotFoundError(f"Prospecting plan not found: {PLAN}")
    if not PRIORITY.exists():
        raise FileNotFoundError(f"Company priority file not found: {PRIORITY}")

    plan = pd.read_csv(PLAN, dtype=str).fillna("")
    priority = pd.read_csv(PRIORITY, dtype=str).fillna("")

    required_plan = [
        "search_id",
        "company_name",
        "company_domain",
        "role_category",
    ]
    required_priority = [
        "company_domain",
        "priority_rank",
        "priority_tier",
        "priority_score",
        "monthly_visits",
    ]

    missing_plan = [col for col in required_plan if col not in plan.columns]
    missing_priority = [
        col for col in required_priority if col not in priority.columns
    ]

    if missing_plan:
        raise ValueError(f"Missing plan columns: {missing_plan}")
    if missing_priority:
        raise ValueError(f"Missing priority columns: {missing_priority}")

    if plan["search_id"].astype(str).str.strip().eq("").any():
        raise ValueError("The prospecting plan contains an empty search_id.")

    if priority["company_domain"].astype(str).str.strip().eq("").any():
        raise ValueError("The company priority file contains an empty domain.")

    duplicate_domains = priority[
        priority["company_domain"].duplicated(keep=False)
    ]["company_domain"].unique()

    if len(duplicate_domains):
        raise ValueError(
            "Company priority file must contain one row per domain. "
            f"Duplicate domains: {list(duplicate_domains[:10])}"
        )

    return plan, priority


def attach_company_ids(frame):
    """Resolve local SQLite company IDs for independent runner-side checks."""

    company_ids = []
    lookup_errors = []

    for domain in frame["company_domain"]:
        try:
            company = get_company_by_domain(str(domain).strip())
            company_ids.append(company["id"] if company else "")
            lookup_errors.append("" if company else "domain_not_found_in_database")
        except Exception as error:
            company_ids.append("")
            lookup_errors.append(f"database_lookup_error: {type(error).__name__}: {error}")

    frame["company_id"] = company_ids
    frame["database_lookup_status"] = [
        "matched" if company_id != "" else "unmatched"
        for company_id in company_ids
    ]
    frame["database_lookup_error"] = lookup_errors
    return frame


def main():
    plan, priority = load_inputs()

    # Preserve the source plan's order as the final tie-breaker.
    plan = plan.copy()
    plan["_plan_order"] = range(len(plan))

    merged = plan.merge(
        priority[
            [
                "company_domain",
                "priority_rank",
                "priority_tier",
                "priority_score",
                "monthly_visits",
            ]
        ],
        on="company_domain",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    merged["monthly_visits_numeric"] = merged["monthly_visits"].apply(
        parse_monthly_visits
    )
    merged["priority_rank_numeric"] = pd.to_numeric(
        merged["priority_rank"], errors="coerce"
    )
    merged["priority_score_numeric"] = pd.to_numeric(
        merged["priority_score"], errors="coerce"
    )

    merged["traffic_eligibility"] = merged["monthly_visits_numeric"].apply(
        lambda visits: (
            "qualified"
            if visits is not None and visits >= MINIMUM_MONTHLY_VISITS
            else "below_threshold"
            if visits is not None
            else "pending"
        )
    )

    merged["queue_exclusion_reason"] = ""
    merged.loc[
        merged["_merge"] != "both",
        "queue_exclusion_reason",
    ] = "company_missing_from_priority_file"
    merged.loc[
        merged["monthly_visits_numeric"].notna()
        & (merged["monthly_visits_numeric"] < MINIMUM_MONTHLY_VISITS),
        "queue_exclusion_reason",
    ] = "monthly_visitors_below_100000"
    merged.loc[
        merged["monthly_visits_numeric"].isna()
        & (merged["_merge"] == "both"),
        "queue_exclusion_reason",
    ] = "monthly_visitors_missing_or_unparseable"

    eligible = merged[
        (merged["_merge"] == "both")
        & (merged["traffic_eligibility"] == "qualified")
    ].copy()

    excluded = merged[
        merged["queue_exclusion_reason"] != ""
    ].copy()

    # Add the SQLite company ID so the execution runner can recheck the
    # authoritative company record immediately before contacting Lusha.
    eligible = attach_company_ids(eligible)

    # Keep rank ascending, score descending, and original plan order stable.
    # The old builder sorted on a non-existent "priority" column.
    eligible = eligible.sort_values(
        by=[
            "priority_rank_numeric",
            "priority_score_numeric",
            "_plan_order",
        ],
        ascending=[True, False, True],
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)

    eligible.insert(0, "execution_order", range(1, len(eligible) + 1))
    eligible["execution_status"] = "pending"

    # Keep numeric visitor count explicit for audit and runner validation.
    eligible["monthly_visits"] = eligible["monthly_visits_numeric"]

    REPORTS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    output_columns = [
        col for col in eligible.columns
        if col not in {"_merge", "_plan_order"}
    ]
    eligible[output_columns].to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    excluded_columns = [
        col for col in excluded.columns
        if col not in {"_merge", "_plan_order"}
    ]
    excluded[excluded_columns].to_csv(
        EXCLUDED_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    summary = (
        eligible.groupby(
            ["priority_tier", "priority_rank", "company_name"],
            dropna=False,
        )
        .agg(
            search_count=("search_id", "count"),
            monthly_visits=("monthly_visits", "first"),
            priority_score=("priority_score", "first"),
        )
        .reset_index()
    )

    if not summary.empty:
        summary["priority_rank_numeric"] = pd.to_numeric(
            summary["priority_rank"], errors="coerce"
        )
        summary = summary.sort_values(
            "priority_rank_numeric",
            na_position="last",
        ).drop(columns=["priority_rank_numeric"])

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        eligible[output_columns].to_excel(
            writer,
            sheet_name="Execution Queue",
            index=False,
        )
        summary.to_excel(
            writer,
            sheet_name="Company Sequence",
            index=False,
        )
        excluded[excluded_columns].to_excel(
            writer,
            sheet_name="Excluded - Traffic Gate",
            index=False,
        )

        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

    print("\nQUIKLEE PRIORITY SEARCH QUEUE")
    print("=" * 55)
    print("Planned searches:", len(merged))
    print("Eligible searches:", len(eligible))
    print("Excluded searches:", len(excluded))
    print(
        "Eligible searches with SQLite company match:",
        int((eligible["database_lookup_status"] == "matched").sum())
        if not eligible.empty else 0,
    )
    print(
        "Eligible searches without SQLite company match:",
        int((eligible["database_lookup_status"] != "matched").sum())
        if not eligible.empty else 0,
    )

    print("\nFirst 15 eligible searches:")
    preview_columns = [
        col for col in [
            "execution_order",
            "search_id",
            "company_id",
            "company_name",
            "role_category",
            "priority_tier",
            "priority_score",
            "monthly_visits",
            "traffic_eligibility",
            "database_lookup_status",
        ]
        if col in eligible.columns
    ]
    if not eligible.empty:
        print(eligible[preview_columns].head(15).to_string(index=False))
    else:
        print("No eligible searches.")

    print("\nCSV:", OUTPUT_CSV)
    print("Excluded CSV:", EXCLUDED_CSV)
    print("Excel:", OUTPUT_EXCEL)
    print("\nNo Lusha API requests were made.")
    print("No Lusha credits were consumed.")


if __name__ == "__main__":
    main()
