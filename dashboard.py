from pathlib import Path
from datetime import datetime
from io import BytesIO
import json
import re

import pandas as pd
import streamlit as st

from database.db import initialize_database
from database.company_repository import update_company

from database.campaign_research_queue import (
    get_campaign_research_queue,
    get_research_queue_summary,
)

from database.campaign_research_controller import (
    build_campaign_research_plan,
    run_campaign_research,
)
from database.campaign_linker import link_campaign_companies

from database.campaign_repository import (
    create_campaign,
    get_all_campaigns,
    get_campaign_records,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports" / "final"
CAMPAIGN_UPLOAD_DIR = DATA_DIR / "campaign_uploads"

st.set_page_config(
    page_title="Quiklee Sales Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Create the SQLite schema on first cloud startup.
initialize_database()

FILES = {
    "crm": DATA_DIR / "Quiklee Sales CRM - Leads.csv",
    "priority": DATA_DIR / "lusha_company_priority.csv",
    "lusha": DATA_DIR / "lusha_discovered_contacts.csv",
    "website_contacts": DATA_DIR / "website_contacts.csv",
    "websites": DATA_DIR / "verified_websites.csv",
    "traffic": DATA_DIR / "traffic_enrichment_results.csv",
}

REPORTS = {
    "Manager Report": REPORT_DIR / "Quiklee_Sales_Intelligence_Manager_Report.xlsx",
    "Lusha Campaign Dashboard": REPORT_DIR / "Lusha_Campaign_Dashboard.xlsx",
    "Lead Prioritisation": REPORT_DIR / "Quiklee_Lead_Prioritization.xlsx",
    "Priority Search Queue": REPORT_DIR / "Lusha_Priority_Search_Queue.xlsx",
}


# --------------------------------------------------
# DATA LOADING
# --------------------------------------------------

@st.cache_data
def load_csv(path_string):
    path = Path(path_string)

    if not path.exists():
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


def get_data(key):
    return load_csv(str(FILES[key]))


def numeric_column(df, column):
    if column not in df.columns:
        return pd.Series(dtype=float)

    return pd.to_numeric(
        df[column],
        errors="coerce",
    )


def display_table(df, height=420):
    if df.empty:
        st.info("No records available in this dataset.")
        return

    st.dataframe(
        df,
        height=height,
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------
# CAMPAIGN HELPERS
# --------------------------------------------------

def normalize_column_name(value):
    """Normalize spreadsheet headers for automatic detection."""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower().strip(),
    )


def detect_column(columns, aliases):
    """Find a column using common header variations."""

    normalized = {
        normalize_column_name(column): column
        for column in columns
    }

    for alias in aliases:
        key = normalize_column_name(alias)

        if key in normalized:
            return normalized[key]

    for key, original in normalized.items():
        for alias in aliases:
            alias_key = normalize_column_name(alias)

            if alias_key and alias_key in key:
                return original

    return None


def read_uploaded_dataset(uploaded_file):
    """Read CSV or Excel files safely."""

    file_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):

        try:
            dataframe = pd.read_csv(
                BytesIO(file_bytes),
                dtype=str,
                encoding="utf-8-sig",
            )

        except UnicodeDecodeError:
            dataframe = pd.read_csv(
                BytesIO(file_bytes),
                dtype=str,
                encoding="latin1",
            )

    elif filename.endswith((".xlsx", ".xls")):

        dataframe = pd.read_excel(
            BytesIO(file_bytes),
            dtype=str,
        )

    else:
        raise ValueError("Unsupported file format.")

    return dataframe.fillna(""), file_bytes


# --------------------------------------------------
# LOAD EXISTING DATA
# --------------------------------------------------

crm = get_data("crm")

# If the original CRM CSV is not present in the cloud deployment,
# use the most recently uploaded CRM campaign saved in SQLite.
if crm.empty:
    try:
        saved_campaigns = get_all_campaigns()
        crm_campaigns = [
            item for item in saved_campaigns
            if "crm" in str(item.get("campaign_name", "")).lower()
            or "crm" in str(item.get("source_filename", "")).lower()
        ]

        if crm_campaigns:
            latest_crm_campaign = crm_campaigns[0]
            saved_rows = get_campaign_records(latest_crm_campaign["id"])
            reconstructed_rows = []

            for saved_row in saved_rows:
                try:
                    original_row = json.loads(
                        saved_row.get("original_row_json") or "{}"
                    )
                except (TypeError, ValueError):
                    original_row = {}

                if isinstance(original_row, dict):
                    reconstructed_rows.append(original_row)

            if reconstructed_rows:
                crm = pd.DataFrame(reconstructed_rows).fillna("")
    except Exception as error:
        st.warning(
            "The uploaded CRM campaign could not be loaded: "
            f"{type(error).__name__}: {error}"
        )

priority = get_data("priority")
lusha = get_data("lusha")
website_contacts = get_data("website_contacts")
websites = get_data("websites")
traffic = get_data("traffic")


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

st.sidebar.title("QUIKLEE")
st.sidebar.caption("Sales Intelligence Platform")

st.sidebar.divider()

if st.sidebar.button("Refresh all data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Overview",
        "CRM Lead Management",
        "Lead Prioritisation",
        "Contact Intelligence",
        "Website Intelligence",
        "Campaign Management",
        "Reports",
    ],
)

st.sidebar.divider()

st.sidebar.caption("Data sources: Local project datasets")
st.sidebar.caption("Mode: Campaign upload and review")


# --------------------------------------------------
# PAGE 1: OVERVIEW
# --------------------------------------------------

if page == "Overview":

    st.title("QUIKLEE SALES INTELLIGENCE")
    st.caption(
        "Unified business discovery, lead prioritisation "
        "and contact intelligence"
    )

    st.divider()

    unique_brands = (
        crm["Brand Name"].nunique()
        if not crm.empty and "Brand Name" in crm.columns
        else 0
    )

    products = 186
    total_contacts = len(lusha)
    priority_companies = len(priority)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("CRM Lead Records", len(crm))
    col2.metric("Unique CRM Brands", unique_brands)
    col3.metric("Prioritised Companies", priority_companies)
    col4.metric("Lusha Contacts", total_contacts)

    st.divider()

    col1, col2, col3 = st.columns(3)

    col1.metric("Researched Companies", 5)
    col2.metric("Product Records", products)
    col3.metric("Website Contact Records", len(website_contacts))

    st.subheader("Lead Priority Distribution")

    if not priority.empty and "priority_tier" in priority.columns:

        tier_counts = (
            priority["priority_tier"]
            .value_counts()
            .reindex(["A", "B", "C"], fill_value=0)
        )

        st.bar_chart(tier_counts)

    st.subheader("Top 10 Priority Companies")

    if not priority.empty:

        top = priority.copy()

        if "priority_rank" in top.columns:

            top["priority_rank"] = numeric_column(
                top,
                "priority_rank",
            )

            top = top.sort_values("priority_rank")

        columns = [
            col for col in [
                "priority_rank",
                "company_name",
                "priority_tier",
                "priority_score",
                "monthly_visits",
                "remaining_role_gaps",
            ]
            if col in top.columns
        ]

        display_table(top[columns].head(10), 350)

    st.info(
        "The overview combines existing project datasets. "
        "Some metrics are sourced from previously generated "
        "reports and are not live API results."
    )


# --------------------------------------------------
# PAGE 2: CRM LEAD MANAGEMENT
# --------------------------------------------------

elif page == "CRM Lead Management":

    st.title("CRM LEAD MANAGEMENT")
    st.caption("Search and review the original Quiklee CRM records.")

    if crm.empty:

        st.warning("CRM dataset is unavailable.")

    else:

        search = st.text_input(
            "Search by brand, contact name, email or role"
        )

        filtered = crm.copy()

        if search.strip():

            searchable = [
                col for col in [
                    "Brand Name",
                    "Full Name",
                    "Email ",
                    "Role",
                    "Website",
                ]
                if col in filtered.columns
            ]

            mask = pd.Series(False, index=filtered.index)

            for col in searchable:

                mask |= filtered[col].str.contains(
                    search.strip(),
                    case=False,
                    na=False,
                    regex=False,
                )

            filtered = filtered[mask]

        status_col = "Lead status"

        if status_col in filtered.columns:

            statuses = sorted(
                value for value in filtered[status_col].unique()
                if value
            )

            selected_statuses = st.multiselect(
                "Filter by lead status",
                statuses,
                default=statuses,
            )

            filtered = filtered[
                filtered[status_col].isin(selected_statuses)
            ]

        st.metric("Matching CRM Records", len(filtered))

        display_table(filtered, 520)

        st.download_button(
            "Download filtered CRM CSV",
            data=filtered.to_csv(index=False).encode("utf-8-sig"),
            file_name="Quiklee_Filtered_CRM_Leads.csv",
            mime="text/csv",
        )


# --------------------------------------------------
# PAGE 3: LEAD PRIORITISATION
# --------------------------------------------------

elif page == "Lead Prioritisation":

    st.title("LEAD PRIORITISATION")
    st.caption(
        "Rank companies using traffic, role gaps and data quality."
    )

    if priority.empty:

        st.warning("Priority dataset is unavailable.")

    else:

        df = priority.copy()

        if "priority_rank" in df.columns:

            df["priority_rank"] = numeric_column(
                df,
                "priority_rank",
            )

            df = df.sort_values("priority_rank")

        col1, col2, col3 = st.columns(3)

        for column, tier in zip(
            [col1, col2, col3],
            ["A", "B", "C"],
        ):

            count = (
                df["priority_tier"].eq(tier).sum()
                if "priority_tier" in df.columns
                else 0
            )

            column.metric(f"Priority {tier} Companies", int(count))

        st.divider()

        if "priority_tier" in df.columns:

            selected_tiers = st.multiselect(
                "Select priority tiers",
                ["A", "B", "C"],
                default=["A", "B", "C"],
            )

            df = df[
                df["priority_tier"].isin(selected_tiers)
            ]

        search = st.text_input("Search company name")

        if search.strip() and "company_name" in df.columns:

            df = df[
                df["company_name"].str.contains(
                    search.strip(),
                    case=False,
                    na=False,
                    regex=False,
                )
            ]

        display_table(df, 520)

        st.download_button(
            "Download prioritisation CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="Quiklee_Lead_Prioritisation.csv",
            mime="text/csv",
        )


# --------------------------------------------------
# PAGE 4: CONTACT INTELLIGENCE
# --------------------------------------------------

elif page == "Contact Intelligence":

    st.title("CONTACT INTELLIGENCE")
    st.caption(
        "Explore the contact intelligence capabilities "
        "of the Quiklee Sales Intelligence platform."
    )

    st.info(
        "Contact records and Lusha integrations are disabled "
        "in this public demonstration to protect confidential "
        "business and contact information."
    )

    st.subheader("Available Capabilities")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Contact Discovery**")
        st.write(
            "Identify relevant business decision-makers "
            "and organise prospect information."
        )

    with col2:
        st.markdown("**Contact Enrichment**")
        st.write(
            "Enrich prospect records with business contact "
            "intelligence through authorised integrations."
        )

    st.caption(
        "Live contact discovery and paid contact reveals "
        "are not available in this public demo."
    )


# --------------------------------------------------
# PAGE 5: WEBSITE INTELLIGENCE
# -------------------------------------------------- 



elif page == "Website Intelligence":

    st.title("WEBSITE INTELLIGENCE")
    st.caption("Website discovery, verification and traffic enrichment.")

    col1, col2 = st.columns(2)

    col1.metric("Website Verification Records", len(websites))
    col2.metric("Traffic Enrichment Records", len(traffic))

    st.subheader("Website Verification")

    if not websites.empty:
        display_table(websites, 400)
    else:
        st.info("No website verification data available.")

    st.divider()

    st.subheader("Traffic Intelligence")

    if not traffic.empty:
        display_table(traffic, 400)
    else:
        st.info("No traffic enrichment records available.")


# --------------------------------------------------
# PAGE 6: CAMPAIGN MANAGEMENT
# --------------------------------------------------

elif page == "Campaign Management":

    st.title("CAMPAIGN MANAGEMENT")

    st.caption(
        "Upload different CRM datasets, create campaigns "
        "and preserve every original lead record."
    )

    st.info(
        "Uploading a dataset does not trigger Lusha searches, "
        "contact reveals or paid API calls."
    )

    st.divider()

    st.subheader("1. Upload a new campaign")

    uploaded_file = st.file_uploader(
        "Upload CSV or Excel dataset",
        type=["csv", "xlsx", "xls"],
        key="campaign_file_uploader",
    )

    if uploaded_file is not None:

        try:

            dataframe, file_bytes = read_uploaded_dataset(
                uploaded_file
            )

            if dataframe.empty:

                st.warning("The uploaded dataset contains no rows.")

            else:

                st.success(
                    f"File loaded successfully: "
                    f"{len(dataframe)} rows and "
                    f"{len(dataframe.columns)} columns."
                )

                st.write("Dataset preview")

                display_table(dataframe.head(10), 300)

                columns = list(dataframe.columns)

                detected_brand = detect_column(
                    columns,
                    [
                        "Brand Name",
                        "Brand",
                        "Company Name",
                        "Company",
                        "Business Name",
                    ],
                )

                detected_website = detect_column(
                    columns,
                    [
                        "Website",
                        "Website URL",
                        "Domain",
                        "Company Website",
                        "URL",
                    ],
                )

                detected_traffic = detect_column(
                    columns,
                    [
                        "Monthly Visitors",
                        "Monthly Visits",
                        "Monthly Traffic",
                        "Monthly Website Visitors",
                        "Visitors",
                    ],
                )

                st.subheader("2. Confirm column mapping")

                st.caption(
                    "Check the detected columns. "
                    "You can change them if your file uses different headers."
                )

                def selected_index(options, detected):
                    if detected in options:
                        return options.index(detected)
                    return 0

                brand_column = st.selectbox(
                    "Brand / Company Name column",
                    columns,
                    index=selected_index(columns, detected_brand),
                )

                website_options = ["Not available"] + columns

                website_default = (
                    detected_website
                    if detected_website in columns
                    else "Not available"
                )

                website_column = st.selectbox(
                    "Website column",
                    website_options,
                    index=website_options.index(website_default),
                )

                traffic_options = ["Not available"] + columns

                traffic_default = (
                    detected_traffic
                    if detected_traffic in columns
                    else "Not available"
                )

                traffic_column = st.selectbox(
                    "Monthly visitors column",
                    traffic_options,
                    index=traffic_options.index(traffic_default),
                )

                campaign_name = st.text_input(
                    "Campaign name",
                    value=Path(uploaded_file.name).stem,
                )

                st.divider()

                st.subheader("3. Create campaign")

                st.caption(
                    "Every non-empty brand row will be saved separately. "
                    "Duplicate brands and their original source rows "
                    "will be preserved."
                )

                if st.button(
                    "Create Campaign",
                    type="primary",
                    use_container_width=True,
                ):

                    if not campaign_name.strip():

                        st.error("Please enter a campaign name.")

                    else:

                        try:

                            CAMPAIGN_UPLOAD_DIR.mkdir(
                                parents=True,
                                exist_ok=True,
                            )

                            timestamp = datetime.now().strftime(
                                "%Y%m%d_%H%M%S_%f"
                            )

                            saved_filename = (
                                f"{timestamp}_{Path(uploaded_file.name).name}"
                            )

                            saved_path = (
                                CAMPAIGN_UPLOAD_DIR / saved_filename
                            )

                            saved_path.write_bytes(file_bytes)

                            mapping = {
                                "brand": brand_column,
                                "website": (
                                    None
                                    if website_column == "Not available"
                                    else website_column
                                ),
                                "monthly_visitors": (
                                    None
                                    if traffic_column == "Not available"
                                    else traffic_column
                                ),
                            }

                            result = create_campaign(
                                dataframe=dataframe.reset_index(drop=True),
                                campaign_name=campaign_name.strip(),
                                source_filename=uploaded_file.name,
                                column_mapping=mapping,
                                source_file_path=str(saved_path),
                            )

                            link_result = link_campaign_companies(
                                result["campaign_id"]
                            )

                            st.success(
                                f"Campaign created successfully! "
                                f"Campaign ID: {result['campaign_id']}"
                            )

                            st.subheader("Company Linking Results")

                            link_col1, link_col2, link_col3, link_col4 = st.columns(4)

                            link_col1.metric(
                                "Linked Records",
                                link_result["linked_records"]
                            )

                            link_col2.metric(
                                "New Companies Created",
                                link_result["new_companies_created"]
                            )

                            link_col3.metric(
                                "Existing Companies Reused",
                                link_result["existing_companies_reused"]
                            )

                            link_col4.metric(
                                "Failed Records",
                                link_result["failed_records"]
                            )

                            col1, col2, col3 = st.columns(3)

                            col1.metric(
                                "Original Rows",
                                result["total_source_rows"],
                            )

                            col2.metric(
                                "Saved Brand Rows",
                                result["saved_rows"],
                            )

                            col3.metric(
                                "Skipped Empty Brand Rows",
                                result["skipped_rows"],
                            )

                            st.info(
                                "Campaign records have been saved. "
                                "No Lusha API calls or contact reveals "
                                "were performed."
                            )

                            st.cache_data.clear()

                        except Exception as error:

                            st.error(
                                f"Campaign creation failed: {error}"
                            )

        except Exception as error:

            st.error(
                f"Unable to read the uploaded file: {error}"
            )

    st.divider()

    # --------------------------------------------------
    # CAMPAIGN HISTORY
    # --------------------------------------------------

    st.subheader("4. Campaign history")

    campaigns = get_all_campaigns()

    if not campaigns:

        st.info(
            "No campaigns created yet. Upload a dataset above "
            "to create your first campaign."
        )

    else:

        campaign_summary = pd.DataFrame(campaigns)

        summary_columns = [
            column for column in [
                "id",
                "campaign_name",
                "source_filename",
                "source_row_count",
                "saved_records",
                "status",
                "created_at",
            ]
            if column in campaign_summary.columns
        ]

        display_table(
            campaign_summary[summary_columns],
            350,
        )

        st.divider()

        st.subheader("5. Inspect campaign records")

        selected_campaign = st.selectbox(
            "Select campaign",
            campaigns,
            format_func=lambda item: (
                f"#{item['id']} - {item['campaign_name']}"
            ),
        )

        records = get_campaign_records(
            selected_campaign["id"]
        )

        if records:

            traffic_counts = pd.Series(
                [
                    record["traffic_status"]
                    for record in records
                ]
            ).value_counts()

            col1, col2, col3 = st.columns(3)

            col1.metric("Saved Records", len(records))

            col2.metric(
                "Traffic Qualified",
                int(traffic_counts.get("qualified", 0)),
            )

            col3.metric(
                "Pending Traffic",
                int(traffic_counts.get("pending", 0)),
            )

            st.subheader("Original campaign rows")

            original_rows = []

            for record in records:

                try:
                    original = json.loads(
                        record["original_row_json"]
                    )
                except (TypeError, ValueError):
                    original = {}

                original["_source_row_number"] = (
                    record["source_row_number"]
                )

                original["_brand_name"] = (
                    record["source_brand_name"]
                )

                original["_monthly_visitors"] = (
                    record["monthly_visits"]
                )

                original["_traffic_status"] = (
                    record["traffic_status"]
                )

                original_rows.append(original)

            records_dataframe = pd.DataFrame(original_rows)

            display_table(records_dataframe, 500)

            st.download_button(
                "Download campaign records CSV",
                data=records_dataframe.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name=(
                    f"campaign_{selected_campaign['id']}_records.csv"
                ),
                mime="text/csv",
            )

        else:

            st.info("No saved records are available for this campaign.")


        st.divider()
        st.subheader("6. Company Research Queue")

        research_queue = get_campaign_research_queue(
            selected_campaign["id"]
        )

        queue_summary = get_research_queue_summary(
            research_queue
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Unique Companies",
            queue_summary["unique_companies"],
        )

        col2.metric(
            "Research Eligible",
            queue_summary["research_eligible"],
        )

        col3.metric(
            "Below Traffic Threshold",
            queue_summary["below_threshold"],
        )

        col4.metric(
            "Pending Verification",
            queue_summary["pending_verification"],
        )

        st.caption(
            "Companies are deduplicated by their linked company ID. "
            "Only brands with at least 100,000 monthly visitors "
            "are eligible for research."
        )

        if research_queue:

            queue_df = pd.DataFrame(research_queue)

            display_columns = [
                "company_id",
                "company_name",
                "website",
                "monthly_visits",
                "traffic_status",
                "research_status",
                "existing_research_records",
                "source_rows",
                "lead_score",
                "lead_category",
            ]

            queue_df = queue_df[
                [
                    column for column in display_columns
                    if column in queue_df.columns
                ]
            ]

            display_table(queue_df, 400)

            missing_websites = [item for item in research_queue if not item.get('website')]
            for company_item in missing_websites:
                website_value = st.text_input(
                    'Official website for ' + company_item['company_name'],
                    value='https://cahoot.in/' if company_item['company_name'].strip().lower() == 'cahoot' else '',
                    key='company_website_' + str(company_item['company_id']),
                )
                if st.button('Save official website', key='save_website_' + str(company_item['company_id'])):
                    if website_value.strip().startswith(('https://', 'http://')):
                        update_company(company_item['company_id'], {'website_url': website_value.strip()})
                        st.success('Website saved.')
                        st.rerun()
                    else:
                        st.error('Enter a full URL beginning with https://')

            st.download_button(
                "Download Research Queue",
                data=queue_df.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name=(
                    f"campaign_{selected_campaign['id']}_research_queue.csv"
                ),
                mime="text/csv",
            )

        else:
            st.info("No companies found in this research queue.")


        st.divider()
        st.subheader("7. Live Research")

        st.caption(
            "Review the plan first. Live execution only starts after explicit "
            "approval. A fresh TabAPI traffic refresh may consume API credits."
        )

        try:
            research_plan = build_campaign_research_plan(
                selected_campaign["id"]
            )
            plan_summary = research_plan["summary"]

            st.write("**Research plan preview**")
            st.json(research_plan)

            col1, col2, col3 = st.columns(3)
            col1.metric("Ready / retry", plan_summary["ready_for_research"] + plan_summary.get("ready_for_retry", 0))
            col2.metric("Already completed", plan_summary["already_completed"])
            col3.metric("Blocked by traffic", plan_summary["blocked_by_traffic"])

            if plan_summary.get("ready_for_retry", 0):
                st.info(str(plan_summary["ready_for_retry"]) + " partially researched/failed company record(s) can be retried after approval.")

            refresh_tabapi = st.checkbox(
                "Refresh monthly traffic from TabAPI (may consume credits)",
                value=False,
                key=f"tabapi_refresh_{selected_campaign['id']}",
            )
            approve_live = st.checkbox(
                "I approve live website research and the selected API usage",
                value=False,
                key=f"approve_live_research_{selected_campaign['id']}",
            )

            if st.button(
                "Run Live Research",
                type="primary",
                disabled=not approve_live or (plan_summary["ready_for_research"] + plan_summary.get("ready_for_retry", 0) == 0),
                key=f"run_live_research_{selected_campaign['id']}",
            ):
                with st.spinner("Running approved company research..."):
                    live_result = run_campaign_research(
                        selected_campaign["id"],
                        execute=True,
                        confirm_external_calls=True,
                        refresh_traffic_api=refresh_tabapi,
                    )
                st.success(
                    f"Research finished. Attempted "
                    f"{live_result.get('companies_attempted', 0)} companies."
                )
                st.json(live_result)
                st.rerun()

            if (plan_summary["ready_for_research"] + plan_summary.get("ready_for_retry", 0)) == 0:
                st.warning(
                    "There are no companies currently marked ready for research. "
                    "Check the traffic eligibility status and research queue first."
                )

        except Exception as error:
            st.error(
                f"Unable to prepare or run the research plan: "
                f"{type(error).__name__}: {error}"
            )

            

# --------------------------------------------------
# PAGE 7: REPORTS
# --------------------------------------------------

elif page == "Reports":

    st.title("REPORT CENTRE")
    st.caption("Download generated project reports.")

    for report_name, report_path in REPORTS.items():

        st.subheader(report_name)

        if report_path.exists():

            with open(report_path, "rb") as file:
                report_bytes = file.read()

            st.download_button(
                label=f"Download {report_name}",
                data=report_bytes,
                file_name=report_path.name,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key=f"download_{report_name}",
            )

            st.caption(
                f"Last modified: "
                f"{pd.Timestamp(report_path.stat().st_mtime, unit='s')}"
            )

        else:

            st.warning(
                f"Report not generated yet: {report_path.name}"
            )

        st.divider()


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.sidebar.caption("Quiklee Sales Intelligence")
st.sidebar.caption("Internal demonstration build")
