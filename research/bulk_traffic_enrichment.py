
import argparse
import time
from pathlib import Path

import pandas as pd

from research.traffic_analysis import analyse_traffic


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = PROJECT_ROOT / "data" / "website_verification_results.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "traffic_enrichment_results.csv"

DELAY_SECONDS = 2


def load_verified_companies(input_file):
    df = pd.read_csv(input_file)

    required_columns = {
        "company_name",
        "domain",
        "verification_status"
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns in input CSV: {sorted(missing)}"
        )

    df = df[
        df["verification_status"].astype(str).str.lower()
        == "likely_company_match"
    ].copy()

    df["domain"] = df["domain"].fillna("").astype(str).str.strip()

    df = df[df["domain"] != ""]
    df = df.drop_duplicates(subset=["domain"], keep="first")

    return df.reset_index(drop=True)


def load_completed_domains(output_file):
    if not output_file.exists():
        return set()

    try:
        previous = pd.read_csv(output_file)

        if "domain" not in previous.columns:
            return set()

        completed = previous[
            previous["status"].astype(str) == "completed"
        ]["domain"]

        return set(completed.dropna().astype(str).str.lower())

    except Exception:
        return set()


def save_result(result, output_file):
    new_row = pd.DataFrame([result])

    if output_file.exists():
        new_row.to_csv(
            output_file,
            mode="a",
            header=False,
            index=False,
            encoding="utf-8-sig"
        )
    else:
        new_row.to_csv(
            output_file,
            index=False,
            encoding="utf-8-sig"
        )


def flatten_traffic_result(company_name, domain, result):
    return {
        "company_name": company_name,
        "domain": domain,
        "monthly_visits": result.get("monthly_visits"),
        "reporting_month": result.get("reporting_month"),
        "global_rank": result.get("global_rank"),
        "country_rank": (
            result.get("country_rank", {}).get("rank")
            if isinstance(result.get("country_rank"), dict)
            else None
        ),
        "bounce_rate": result.get("bounce_rate"),
        "pages_per_visit": result.get("pages_per_visit"),
        "time_on_site_seconds": result.get("time_on_site_seconds"),
        "monthly_history": str(result.get("monthly_history", [])),
        "traffic_sources": str(result.get("traffic_sources", {})),
        "top_regions": str(result.get("top_regions", [])),
        "top_keywords": str(result.get("top_keywords", [])),
        "ai_traffic": str(result.get("ai_traffic")),
        "credits_charged": result.get("credits_charged"),
        "status": result.get("status", "unavailable"),
        "error": result.get("error")
    }


def run_pipeline(input_file, output_file, limit=10, months=3, delay=2):

    companies = load_verified_companies(input_file)

    completed_domains = load_completed_domains(output_file)

    pending = companies[
        ~companies["domain"].str.lower().isin(completed_domains)
    ]

    if limit > 0:
        pending = pending.head(limit)

    print("=" * 60)
    print("QUIKLEE SALES INTELLIGENCE")
    print("BULK WEBSITE TRAFFIC ENRICHMENT")
    print("=" * 60)

    print(f"Verified unique domains: {len(companies)}")
    print(f"Already completed: {len(completed_domains)}")
    print(f"Pending in this run: {len(pending)}")
    print(f"Months requested per domain: {months}")
    print(f"Output file: {output_file}")

    if pending.empty:
        print("\nNo pending companies to process.")
        return

    print(
        "\nEstimated maximum credits for this run:",
        len(pending) * months
    )

    successful = 0
    failed = 0

    for index, (_, company) in enumerate(pending.iterrows(), start=1):

        company_name = str(company["company_name"]).strip()
        domain = str(company["domain"]).strip().lower()

        print(f"\n[{index}/{len(pending)}] {company_name} ({domain})")

        result = analyse_traffic(domain, months=months)

        row = flatten_traffic_result(
            company_name,
            domain,
            result
        )

        save_result(row, output_file)

        if result.get("status") == "completed":
            successful += 1
            print("Traffic lookup successful.")
            print("Monthly visits:", result.get("monthly_visits"))
            print("Credits charged:", result.get("credits_charged"))
        else:
            failed += 1
            print("Traffic lookup failed:", result.get("error"))

        if index < len(pending):
            time.sleep(delay)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETED")
    print("=" * 60)
    print("Successful:", successful)
    print("Failed:", failed)
    print("Output:", output_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Bulk TabAPI traffic enrichment"
    )

    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT)
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT)
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10
    )

    parser.add_argument(
        "--months",
        type=int,
        default=3
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_SECONDS
    )

    args = parser.parse_args()

    run_pipeline(
        input_file=Path(args.input),
        output_file=Path(args.output),
        limit=args.limit,
        months=args.months,
        delay=args.delay
    )


