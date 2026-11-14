
import ast
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "traffic_enrichment_results.csv"
OUTPUT_FILE = PROJECT_ROOT / "reports" / "final" / "Quiklee_Traffic_Intelligence_Report.xlsx"

MINIMUM_MONTHLY_VISITS = 100000


def parse_dict(value):
    if isinstance(value, dict):
        return value

    try:
        parsed = ast.literal_eval(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def parse_list(value):
    if isinstance(value, list):
        return value

    try:
        parsed = ast.literal_eval(str(value))
        return parsed if isinstance(parsed, list) else []
    except (ValueError, SyntaxError):
        return []


def load_traffic_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Traffic results file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required = [
        "company_name",
        "domain",
        "monthly_visits",
        "status"
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["monthly_visits"] = pd.to_numeric(
        df["monthly_visits"], errors="coerce"
    )

    return df


def build_company_report(df):
    report = df.copy()

    report["qualification_status"] = report.apply(
        lambda row: (
            "QUALIFIED"
            if row["status"] == "completed"
            and pd.notna(row["monthly_visits"])
            and row["monthly_visits"] > MINIMUM_MONTHLY_VISITS
            else "DISCARDED"
        ),
        axis=1
    )

    report["country_rank_number"] = report["country_rank"].apply(
        lambda value: parse_dict(value).get("rank")
    ) if "country_rank" in report.columns else None

    report["india_traffic_share"] = report["top_regions"].apply(
        lambda value: next(
            (
                region.get("share")
                for region in parse_list(value)
                if region.get("country") == "IN"
            ),
            None
        )
    ) if "top_regions" in report.columns else None

    report["organic_search_share"] = report["traffic_sources"].apply(
        lambda value: parse_dict(value).get("search_organic")
    ) if "traffic_sources" in report.columns else None

    report["paid_search_share"] = report["traffic_sources"].apply(
        lambda value: parse_dict(value).get("search_paid")
    ) if "traffic_sources" in report.columns else None

    report["organic_social_share"] = report["traffic_sources"].apply(
        lambda value: parse_dict(value).get("social_organic")
    ) if "traffic_sources" in report.columns else None

    report["paid_social_share"] = report["traffic_sources"].apply(
        lambda value: parse_dict(value).get("social_paid")
    ) if "traffic_sources" in report.columns else None

    return report


def build_summary(report):
    successful = report[report["status"] == "completed"]
    qualified = report[report["qualification_status"] == "QUALIFIED"]
    discarded = report[report["qualification_status"] == "DISCARDED"]

    summary = pd.DataFrame([
        ["Total companies processed", len(report)],
        ["Successful traffic lookups", len(successful)],
        ["Failed traffic lookups", len(report) - len(successful)],
        ["Qualified companies (>1 lakh visits)", len(qualified)],
        ["Discarded companies (1 lakh or below)", len(discarded)],
        ["Minimum monthly visitors required", MINIMUM_MONTHLY_VISITS],
        [
            "Credits consumed",
            pd.to_numeric(
                successful["credits_charged"], errors="coerce"
            ).sum()
            if "credits_charged" in successful.columns else 0
        ]
    ], columns=["Metric", "Value"])

    return summary


def format_excel(writer):
    workbook = writer.book

    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor="17365D"
            )
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = get_column_letter(column_cells[0].column)

            for cell in column_cells:
                value = str(cell.value) if cell.value is not None else ""
                max_length = max(max_length, len(value))

            worksheet.column_dimensions[column_letter].width = min(
                max(max_length + 2, 14),
                45
            )

        worksheet.row_dimensions[1].height = 25


def generate_report():
    df = load_traffic_data()
    report = build_company_report(df)

    qualified = report[
        report["qualification_status"] == "QUALIFIED"
    ].copy()

    discarded = report[
        report["qualification_status"] == "DISCARDED"
    ].copy()

    summary = build_summary(report)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:

        summary.to_excel(
            writer,
            sheet_name="Executive Summary",
            index=False
        )

        qualified.to_excel(
            writer,
            sheet_name="Qualified Companies",
            index=False
        )

        discarded.to_excel(
            writer,
            sheet_name="Discarded Companies",
            index=False
        )

        report.to_excel(
            writer,
            sheet_name="All Traffic Results",
            index=False
        )

        format_excel(writer)

    print("=" * 55)
    print("QUIKLEE TRAFFIC INTELLIGENCE REPORT")
    print("=" * 55)

    print("Companies processed:", len(report))
    print("Qualified:", len(qualified))
    print("Discarded:", len(discarded))
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    generate_report()
