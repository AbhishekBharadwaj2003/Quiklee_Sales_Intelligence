from pathlib import Path
from datetime import datetime
from io import BytesIO
import json
import re

import pandas as pd
import streamlit as st

from database.db import initialize_database
from database.company_repository import update_company, get_all_companies

from database.campaign_research_queue import (
    get_campaign_research_queue,
    get_research_queue_summary,
)

from database.campaign_research_controller import (
    build_campaign_research_plan,
    run_campaign_research,
)
from database.campaign_linker import link_campaign_companies
from enrichment.lusha_reveal_ui import render_lusha_reveal_ui
from enrichment.lusha_discovery_ui import render_lusha_discovery_ui
from campaign_workflow import get_campaign_traffic_candidates, run_single_company_traffic_validation, score_campaign_leads, get_campaign_intelligence, build_campaign_report, reset_campaign_traffic_to_pending

from database.campaign_repository import (
    create_campaign,
    get_all_campaigns,
    get_campaign_records,
    delete_campaign,
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
    st.caption("Rank companies using verified traffic and available research evidence.")
    campaigns_for_scores = get_all_campaigns()
    if campaigns_for_scores:
        chosen_score_campaign = st.selectbox("Select campaign", campaigns_for_scores, format_func=lambda item: "#" + str(item["id"]) + " - " + item["campaign_name"], key="score_campaign_selector")
        live_scores = get_campaign_intelligence(chosen_score_campaign["id"])
        if not live_scores.empty:
            live_scores = live_scores.sort_values("lead_score", ascending=False, na_position="last")
            display_table(live_scores, 520)
            st.download_button("Download live lead prioritisation", live_scores.to_csv(index=False).encode("utf-8-sig"), file_name="campaign_" + str(chosen_score_campaign["id"]) + "_lead_prioritisation.csv", mime="text/csv")
        else:
            st.info("Run TabAPI validation and lead scoring from Campaign Management first.")
    else:
        st.info("Upload a campaign first.")

# --------------------------------------------------
# PAGE 4: CONTACT INTELLIGENCE
# --------------------------------------------------

elif page == "Contact Intelligence":

    st.title("CONTACT INTELLIGENCE")
    st.caption("Select a prioritised company, discover decision-makers, then reveal selected contact fields with separate approval.")
    companies = get_all_companies()
    companies = sorted(companies, key=lambda item: (item.get("qualification_score") is None, -(item.get("qualification_score") or 0)))
    scored_companies = [item for item in companies if item.get("qualification_score") is not None]
    if not scored_companies:
        st.info("No scored companies yet. Complete TabAPI validation and lead scoring first.")
    else:
        company = st.selectbox("Select prioritised company", scored_companies, format_func=lambda item: item["company_name"] + " — " + str(round(item["qualification_score"], 2)), key="lusha_company_selector")
        st.metric("Lead score", f"{company['qualification_score']:.2f}")
        st.caption("Prospecting search may be restricted by your Lusha API subscription. Email and phone reveals are separate API operations.")
        render_lusha_discovery_ui(FILES["lusha"], company["id"], company["company_name"], company.get("website_url"))
        st.divider()
        st.subheader("Saved contact records and approved reveals")
        if FILES["lusha"].exists():
            saved_contacts = pd.read_csv(FILES["lusha"], dtype=str).fillna("")
            if not saved_contacts.empty:
                display_cols = [col for col in ["contact_name", "designation", "company_name", "linkedin_url", "lusha_contact_id", "enrichment_status"] if col in saved_contacts.columns]
                display_table(saved_contacts[display_cols], 350)
                render_lusha_reveal_ui(FILES["lusha"])
            else:
                st.info("No contact records saved yet.")
        else:
            st.info("No contact records saved yet. Lusha prospecting access may need to be enabled for your API account.")

# --------------------------------------------------
# PAGE 5: WEBSITE INTELLIGENCE
# -------------------------------------------------- 



elif page == "Website Intelligence":

    st.title("WEBSITE INTELLIGENCE")
    st.caption("TabAPI monthly visitor validation and website metrics.")
    website_campaigns = get_all_campaigns()
    if website_campaigns:
        selected_website_campaign = st.selectbox("Select campaign", website_campaigns, format_func=lambda item: "#" + str(item["id"]) + " - " + item["campaign_name"], key="website_campaign_selector")
        website_data = get_campaign_intelligence(selected_website_campaign["id"])
        if not website_data.empty:
            col1, col2, col3 = st.columns(3)
            col1.metric("Companies", len(website_data))
            col2.metric("Traffic qualified", int((website_data["traffic_status"] == "qualified").sum()))
            col3.metric("Below threshold", int((website_data["traffic_status"] == "below_threshold").sum()))
            display_table(website_data, 520)
            st.download_button("Download website intelligence", website_data.to_csv(index=False).encode("utf-8-sig"), file_name="campaign_" + str(selected_website_campaign["id"]) + "_website_intelligence.csv", mime="text/csv")
        else:
            st.info("No linked company results yet.")
    else:
        st.info("Upload and approve a campaign first.")

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

                approve_campaign_upload = st.checkbox("I approve importing this dataset and linking its company records.", key="approve_campaign_upload")

                if st.button(
                    "Create Campaign",
                    type="primary",
                    use_container_width=True,
                    disabled=not approve_campaign_upload,
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
        st.info("No campaigns created yet. Upload a dataset above to create your first campaign.")
    else:
        st.caption("Each campaign has its own delete control. Deleting removes that campaign and its uploaded rows, but preserves shared company profiles.")
        for campaign in campaigns:
            row_left, row_meta, row_action = st.columns([5, 3, 1])
            with row_left:
                st.markdown("**#" + str(campaign["id"]) + " · " + str(campaign["campaign_name"]) + "**")
                st.caption(str(campaign.get("source_filename") or "No source filename"))
            with row_meta:
                st.caption(str(campaign.get("saved_records", 0)) + " records · " + str(campaign.get("status", "")))
                st.caption("Created: " + str(campaign.get("created_at") or "—"))
            with row_action:
                if st.button("🗑️ Delete", key="delete_campaign_" + str(campaign["id"]), type="secondary", help="Delete this campaign"):
                    st.session_state["pending_campaign_delete"] = campaign["id"]

        pending_delete = st.session_state.get("pending_campaign_delete")
        if pending_delete is not None:
            target = next((item for item in campaigns if item["id"] == pending_delete), None)
            if target:
                st.warning("Confirm permanent deletion of campaign #" + str(target["id"]) + " — " + str(target["campaign_name"]) + ". Its campaign rows will be removed; shared company profiles will remain.")
                confirm_col, cancel_col = st.columns(2)
                with confirm_col:
                    if st.button("Confirm delete", type="primary", key="confirm_delete_campaign"):
                        deleted = delete_campaign(pending_delete)
                        st.session_state.pop("pending_campaign_delete", None)
                        if deleted:
                            st.success("Campaign deleted successfully.")
                        st.rerun()
                with cancel_col:
                    if st.button("Cancel", key="cancel_delete_campaign"):
                        st.session_state.pop("pending_campaign_delete", None)
                        st.rerun()
        with st.expander("View campaign summary table"):
            campaign_summary = pd.DataFrame(campaigns)
            summary_columns = [column for column in ["id", "campaign_name", "source_filename", "source_row_count", "saved_records", "status", "created_at"] if column in campaign_summary.columns]
            display_table(campaign_summary[summary_columns], 350)

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
        st.subheader("7. Validate website traffic with TabAPI")
        st.caption(
            "Choose one company at a time. Selecting a company does not use credits; "
            "only clicking the research button sends one TabAPI request."
        )

        campaign_id = selected_campaign["id"]
        tabapi_candidates = get_campaign_traffic_candidates(campaign_id)

        tabapi_result_key = "tabapi_single_result_" + str(campaign_id)
        tabapi_error_key = "tabapi_single_error_" + str(campaign_id)

        selected_company_id = None

        if tabapi_candidates:
            candidate_by_id = {
                item["company_id"]: item for item in tabapi_candidates
            }

            selected_company_id = st.selectbox(
                "Select a company for traffic research",
                options=list(candidate_by_id.keys()),
                format_func=lambda company_id: (
                    candidate_by_id[company_id]["company_name"]
                    + " — "
                    + (
                        candidate_by_id[company_id]["domain"]
                        or "Website missing"
                    )
                ),
                key="tabapi_company_select_" + str(campaign_id),
            )

            selected_company = candidate_by_id[selected_company_id]

            detail_col1, detail_col2 = st.columns(2)
            with detail_col1:
                st.write("**Website**")
                st.write(selected_company["website"] or "Not available")
            with detail_col2:
                st.write("**Current status**")
                st.write(selected_company["traffic_status"].replace("_", " ").title())

            approve_tabapi = st.checkbox(
                "I approve one TabAPI traffic lookup for the selected company. This request may consume API credits.",
                key="approve_tabapi_single_" + str(campaign_id),
            )

            if st.button(
                "Research selected company",
                type="primary",
                disabled=not approve_tabapi,
                key="validate_tabapi_single_" + str(campaign_id),
            ):
                st.session_state.pop(tabapi_result_key, None)
                st.session_state.pop(tabapi_error_key, None)

                try:
                    with st.spinner(
                        "Checking "
                        + selected_company["company_name"]
                        + " with TabAPI..."
                    ):
                        st.session_state[tabapi_result_key] = (
                            run_single_company_traffic_validation(
                                campaign_id,
                                selected_company_id,
                            )
                        )
                except Exception as error:
                    st.session_state[tabapi_error_key] = {
                        "company_id": selected_company_id,
                        "company": selected_company["company_name"],
                        "message": type(error).__name__ + ": " + str(error),
                    }

                st.rerun()

        else:
            st.success(
                "There are no companies awaiting TabAPI traffic validation "
                "in this campaign."
            )

        # Display a result only when it belongs to the currently selected company.
        saved_tabapi_result = st.session_state.get(tabapi_result_key)
        if (
            saved_tabapi_result
            and selected_company_id is not None
            and saved_tabapi_result.get("company_id") == selected_company_id
        ):
            if saved_tabapi_result.get("traffic_status") == "qualified":
                st.success(
                    saved_tabapi_result["company"]
                    + " qualified with "
                    + f'{saved_tabapi_result["monthly_visits"]:,.0f}'
                    + " monthly visits."
                )
            elif saved_tabapi_result.get("traffic_status") == "below_threshold":
                st.warning(
                    saved_tabapi_result["company"]
                    + " is below the required traffic threshold. "
                    + f'{saved_tabapi_result["monthly_visits"]:,.0f}'
                    + " monthly visits."
                )
            else:
                st.error(
                    saved_tabapi_result.get("error")
                    or "TabAPI did not return a usable traffic figure. "
                       "The company remains pending."
                )

            st.dataframe(
                pd.DataFrame([saved_tabapi_result]),
                use_container_width=True,
                hide_index=True,
            )

        saved_tabapi_error = st.session_state.get(tabapi_error_key)
        if (
            saved_tabapi_error
            and selected_company_id is not None
            and saved_tabapi_error.get("company_id") == selected_company_id
        ):
            st.error(
                "TabAPI lookup failed for "
                + saved_tabapi_error["company"]
                + ": "
                + saved_tabapi_error["message"]
            )

        remaining_count = len(get_campaign_traffic_candidates(campaign_id))
        st.caption(
            str(remaining_count)
            + " companies are currently awaiting individual TabAPI validation."
        )

        st.caption(
            "Only successful TabAPI results are saved as verified traffic. "
            "A lookup error does not qualify or disqualify a company. "
            "The qualification rule is strictly greater than 100,000 monthly visits."
        )

        reset_confirm = st.checkbox(
            "I understand this will clear the verified visitor figures for this campaign and return all its companies to pending TabAPI validation.",
            key="reset_traffic_confirm_" + str(campaign_id),
        )
        if st.button(
            "Reset this campaign's traffic to pending",
            disabled=not reset_confirm,
            key="reset_traffic_" + str(campaign_id),
        ):
            reset_count = reset_campaign_traffic_to_pending(campaign_id)
            st.session_state.pop(tabapi_result_key, None)
            st.session_state.pop(tabapi_error_key, None)
            st.success(
                str(reset_count)
                + " campaign records returned to pending. "
                  "Original spreadsheet data is preserved."
            )
            st.rerun()

        st.subheader("8. Calculate lead scores")
        if st.button("Score qualified companies", key="score_campaign_" + str(selected_campaign["id"])):
            score_results = score_campaign_leads(selected_campaign["id"])
            st.dataframe(pd.DataFrame(score_results), use_container_width=True, hide_index=True)
            st.success("Lead scoring completed for eligible companies.")
            st.rerun()

        st.subheader("9. Live Research")

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

            st.info(
                "Bulk Live Research execution is temporarily disabled. "
                "Use the controlled 10-company TabAPI batch above first; "
                "this prevents an accidental all-company API run."
            )

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
    st.caption("Generate and download campaign intelligence reports.")
    report_campaigns = get_all_campaigns()
    if report_campaigns:
        report_campaign = st.selectbox("Select campaign for report", report_campaigns, format_func=lambda item: "#" + str(item["id"]) + " - " + item["campaign_name"], key="report_campaign_selector")
        if st.button("Generate campaign Excel report", type="primary", key="generate_campaign_report"):
            try:
                report_bytes = build_campaign_report(report_campaign["id"])
                st.session_state["generated_campaign_report"] = report_bytes
                st.session_state["generated_campaign_report_name"] = "Quiklee_Campaign_" + str(report_campaign["id"]) + "_Intelligence.xlsx"
                st.success("Campaign report generated.")
            except Exception as error:
                st.error("Report generation failed: " + str(error))
        if st.session_state.get("generated_campaign_report"):
            st.download_button("Download campaign report", st.session_state["generated_campaign_report"], file_name=st.session_state["generated_campaign_report_name"], mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Create a campaign before generating reports.")
    st.divider()
    for report_name, report_path in REPORTS.items():
        if report_path.exists():
            with open(report_path, "rb") as file:
                report_bytes = file.read()
            st.download_button(label="Download " + report_name, data=report_bytes, file_name=report_path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_" + report_name)
        

# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.sidebar.caption("Quiklee Sales Intelligence")
st.sidebar.caption("Internal demonstration build")
