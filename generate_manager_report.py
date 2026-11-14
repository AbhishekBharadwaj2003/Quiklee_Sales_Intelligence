
import sqlite3
import json
from pathlib import Path
from datetime import datetime

import pandas as pd

from reports.lusha_reveal_summary import create_lusha_reveal_summary

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
REPORT_DIR = PROJECT_ROOT / "reports" / "final"

DATABASE_PATH = PROJECT_ROOT / "quiklee_sales.db"
REPORT_PATH = REPORT_DIR / "Quiklee_Sales_Intelligence_Manager_Report.xlsx"

REPORT_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDED_COMPANIES = {"Test Quiklee Brand"}
UNAVAILABLE = "Unavailable"

SOURCE_FILES = {
    "CRM Lead Pipeline": "Quiklee Sales CRM - Leads.csv",
    "Lusha Discovered Contacts": "lusha_discovered_contacts.csv",
    "Lead Prioritisation": "lusha_company_priority.csv",
    "Website Contacts": "website_contacts.csv",
    "Website Verification": "verified_websites.csv",
}


# --------------------------------------------------
# STYLING
# --------------------------------------------------

NAVY = "17365D"
WHITE = "FFFFFF"
LIGHT_BLUE = "D9EAF7"

THIN_BORDER = Border(
    bottom=Side(style="thin", color="D9E1F2")
)


def style_worksheet(ws):
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 34

    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(
            name="Aptos",
            bold=True,
            color=WHITE,
            size=10,
        )
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(
                name="Aptos",
                size=10,
                color="222222",
            )
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )
            cell.border = THIN_BORDER

    for column_cells in ws.columns:
        column_letter = get_column_letter(
            column_cells[0].column
        )

        max_length = 0

        for cell in column_cells:
            if cell.value is not None:
                max_length = max(
                    max_length,
                    min(len(str(cell.value)), 45),
                )

        ws.column_dimensions[column_letter].width = min(
            max(max_length + 3, 14),
            45,
        )


def add_excel_table(ws, table_name):
    if ws.max_row < 2 or ws.max_column < 1:
        return

    reference = (
        f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    )

    table = Table(
        displayName=table_name,
        ref=reference,
    )

    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )

    ws.add_table(table)


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_database_connection():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def get_companies(connection):
    rows = connection.execute("""
        SELECT *
        FROM companies
        ORDER BY id
    """).fetchall()

    return [
        dict(row)
        for row in rows
        if row["company_name"] not in EXCLUDED_COMPANIES
    ]


def get_latest_research(connection, company_id, research_type):
    row = connection.execute("""
        SELECT *
        FROM research_history
        WHERE company_id = ?
        AND research_type = ?
        ORDER BY id DESC
        LIMIT 1
    """, (company_id, research_type)).fetchone()

    if not row:
        return None

    record = dict(row)

    try:
        record["findings"] = json.loads(
            record["findings"] or "{}"
        )
    except (TypeError, json.JSONDecodeError):
        record["findings"] = {}

    return record


def safe_value(value):
    if value is None or value == "":
        return UNAVAILABLE

    return value


# --------------------------------------------------
# CSV HELPERS
# --------------------------------------------------

def load_csv(filename):
    path = DATA_DIR / filename

    if not path.exists():
        print(f"WARNING: Missing source file: {filename}")
        return pd.DataFrame()

    try:
        return pd.read_csv(
            path,
            dtype=str,
            encoding="utf-8-sig",
        ).fillna("")

    except pd.errors.EmptyDataError:
        return pd.DataFrame()

    except UnicodeDecodeError:
        return pd.read_csv(
            path,
            dtype=str,
            encoding="latin1",
        ).fillna("")


def add_dataframe_sheet(wb, sheet_name, filename, table_name):
    df = load_csv(filename)

    ws = wb.create_sheet(sheet_name)

    if df.empty and len(df.columns) == 0:
        ws.append(["No source records available"])
        style_worksheet(ws)
        print(f"{sheet_name}: No records")
        return 0

    ws.append(list(df.columns))

    for row in df.itertuples(index=False, name=None):
        ws.append([
            None if pd.isna(value) else value
            for value in row
        ])

    style_worksheet(ws)
    add_excel_table(ws, table_name)

    print(f"{sheet_name}: {len(df)} records")

    return len(df)


# --------------------------------------------------
# SHEET 1: COMPANY OVERVIEW
# --------------------------------------------------

def create_company_overview(wb, companies):
    ws = wb.active
    ws.title = "Company Overview"

    headers = [
        "Company ID",
        "Company Name",
        "Category",
        "Website",
        "Headquarters",
        "Validation Status",
        "Research Status",
        "Lead Score",
        "Qualification Category",
        "Data Completeness (%)",
        "Enrichment Status",
    ]

    ws.append(headers)

    for company in companies:
        ws.append([
            company["id"],
            company["company_name"],
            safe_value(company["category"]),
            safe_value(company["website_url"]),
            safe_value(company["headquarters"]),
            safe_value(company["validation_status"]),
            safe_value(company["research_status"]),
            company["qualification_score"],
            safe_value(company["qualification_category"]),
            company["data_completeness"],
            safe_value(company["enrichment_status"]),
        ])

    for row in range(2, ws.max_row + 1):
        score_cell = ws.cell(row, 8)
        category_cell = ws.cell(row, 9)

        if score_cell.value is not None:
            score_cell.number_format = "0.00"

            category_cell.fill = PatternFill(
                "solid",
                fgColor="FFF2CC",
            )

        completeness = ws.cell(row, 10)

        if completeness.value == 0:
            completeness.fill = PatternFill(
                "solid",
                fgColor="FCE4D6",
            )

    style_worksheet(ws)
    add_excel_table(ws, "CompanyOverview")


# --------------------------------------------------
# SHEET 2: PRODUCT INTELLIGENCE
# --------------------------------------------------

def create_product_intelligence(wb, connection, companies):
    ws = wb.create_sheet("Product Intelligence")

    headers = [
        "Company",
        "Product Name",
        "Brand",
        "SKU",
        "Category",
        "Displayed Price",
        "Currency",
        "Average Rating",
        "Ratings Count",
        "Reviews Count",
        "Available Sizes",
        "Variant Count",
        "Inventory Quantity",
        "Product URL",
        "Data Source",
    ]

    ws.append(headers)

    total_products = 0

    for company in companies:
        research = get_latest_research(
            connection,
            company["id"],
            "website_research",
        )

        if not research:
            continue

        findings = research["findings"]
        products = findings.get("products", [])

        if not isinstance(products, list):
            continue

        for product in products:
            ws.append([
                company["company_name"],
                safe_value(product.get("product_name")),
                safe_value(product.get("brand")),
                safe_value(product.get("sku")),
                safe_value(product.get("category")),
                product.get("displayed_price"),
                safe_value(product.get("currency")),
                product.get("average_rating"),
                product.get("total_ratings_count"),
                product.get("total_reviews_count"),
                ", ".join(
                    product.get("available_sizes", [])
                ) if product.get("available_sizes") else UNAVAILABLE,
                product.get("variant_count"),
                product.get("inventory_quantity"),
                safe_value(product.get("product_url")),
                safe_value(product.get("source")),
            ])

            total_products += 1

    style_worksheet(ws)
    add_excel_table(ws, "ProductIntelligence")

    return total_products


# --------------------------------------------------
# SHEET 3: RESEARCH AND DATA GAPS
# --------------------------------------------------

def create_research_gaps(wb, connection, companies):
    ws = wb.create_sheet("Research & Data Gaps")

    headers = [
        "Company",
        "Research Type",
        "Source",
        "Confidence",
        "Research Date",
        "Research Findings",
        "Data Availability",
    ]

    ws.append(headers)

    research_types = [
        "website_research",
        "traffic_analysis",
        "business_metrics",
        "funding_research",
        "fallback_research",
    ]

    for company in companies:
        for research_type in research_types:
            research = get_latest_research(
                connection,
                company["id"],
                research_type,
            )

            if not research:
                ws.append([
                    company["company_name"],
                    research_type,
                    UNAVAILABLE,
                    UNAVAILABLE,
                    UNAVAILABLE,
                    "No research record found.",
                    "Not researched",
                ])
                continue

            findings = research["findings"]

            if not isinstance(findings, dict):
                findings = {}

            findings_text = json.dumps(
                findings,
                ensure_ascii=False,
                default=str,
            )

            ws.append([
                company["company_name"],
                research_type,
                safe_value(research.get("source")),
                safe_value(research.get("confidence")),
                safe_value(research.get("researched_at")),
                findings_text,
                safe_value(research.get("confidence")),
            ])

    style_worksheet(ws)
    add_excel_table(ws, "ResearchDataGaps")


# --------------------------------------------------
# MAIN REPORT
# --------------------------------------------------

def generate_report():
    print("\nQUIKLEE SALES INTELLIGENCE")
    print("=" * 60)

    connection = get_database_connection()

    try:
        companies = get_companies(connection)

        if not companies:
            raise ValueError(
                "No eligible company records found."
            )

        print("Researched companies:", len(companies))

        wb = Workbook()

        # Existing three sheets
        create_company_overview(wb, companies)

        product_count = create_product_intelligence(
            wb,
            connection,
            companies,
        )

        create_research_gaps(
            wb,
            connection,
            companies,
        )

        print("Product records:", product_count)

        # Additional five source-data sheets
        crm_count = add_dataframe_sheet(
            wb,
            "CRM Lead Pipeline",
            SOURCE_FILES["CRM Lead Pipeline"],
            "CRMLeadPipeline",
        )

        lusha_count = add_dataframe_sheet(
            wb,
            "Lusha Discovered Contacts",
            SOURCE_FILES["Lusha Discovered Contacts"],
            "LushaDiscoveredContacts",
        )

        create_lusha_reveal_summary(
            wb,
            DATA_DIR / SOURCE_FILES["Lusha Discovered Contacts"],
        )

        priority_count = add_dataframe_sheet(
            wb,
            "Lead Prioritisation",
            SOURCE_FILES["Lead Prioritisation"],
            "LeadPrioritisation",
        )

        website_contact_count = add_dataframe_sheet(
            wb,
            "Website Contacts",
            SOURCE_FILES["Website Contacts"],
            "WebsiteContacts",
        )

        website_verification_count = add_dataframe_sheet(
            wb,
            "Website Verification",
            SOURCE_FILES["Website Verification"],
            "WebsiteVerification",
        )

        # Workbook metadata
        wb.properties.title = (
            "Quiklee Sales Intelligence Manager Report"
        )

        wb.properties.subject = (
            "CRM, Company Research, Product Intelligence, "
            "Lead Prioritisation and Contact Discovery"
        )

        wb.properties.creator = "Quiklee Sales Intelligence"

        wb.properties.description = (
            "Consolidated report generated from the project "
            "database and source CSV files."
        )

        wb.save(REPORT_PATH)

        print("\nREPORT GENERATED SUCCESSFULLY")
        print("=" * 60)

        print("Researched companies:", len(companies))
        print("Products:", product_count)
        print("CRM records:", crm_count)
        print("Lusha contacts:", lusha_count)
        print("Prioritised companies:", priority_count)
        print("Website contact records:", website_contact_count)
        print("Website verification records:", website_verification_count)

        print("Worksheets:", len(wb.sheetnames))

        for sheet in wb.sheetnames:
            print("-", sheet)

        print("\nReport location:")
        print(REPORT_PATH)

    finally:
        connection.close()


if __name__ == "__main__":
    try:
        generate_report()

    except Exception as error:
        print("\nREPORT GENERATION FAILED")
        print(error)
        raise
