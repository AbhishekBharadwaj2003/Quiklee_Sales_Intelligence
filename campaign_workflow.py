from io import BytesIO
import pandas as pd

from database.db import get_db
from database.company_repository import get_company_by_id, update_company
from database.research_repository import add_research_record
from research.traffic_analysis import analyse_traffic
from qualification.qualification_pipeline import qualify_company
from research.research_pipeline import run_company_research
from database.research_repository import get_company_research_history

TRAFFIC_THRESHOLD = 100000


def run_campaign_traffic_validation(campaign_id, months=3):
    """Fetch TabAPI traffic once per unique linked company and save results."""
    with get_db() as connection:
        rows = connection.execute(
            "SELECT id, company_id, source_brand_name, website FROM campaign_records WHERE campaign_id=? ORDER BY source_row_number",
            (campaign_id,),
        ).fetchall()
    unique = {}
    for row in rows:
        item = dict(row)
        if item.get('company_id'):
            existing = unique.get(item['company_id'])
            if existing is None or (not existing.get('website') and item.get('website')):
                unique[item['company_id']] = item
    results = []
    for company_id, item in unique.items():
        company = get_company_by_id(company_id) or {}
        website = item.get('website') or company.get('website_url') or ''
        domain = str(website).strip().replace('https://', '').replace('http://', '').split('/')[0].lower().removeprefix('www.')
        if not domain:
            results.append({'company': item['source_brand_name'], 'domain': '', 'monthly_visits': None, 'traffic_status': 'pending', 'error': 'Website URL missing'})
            continue
        if not company.get('website_url'):
            update_company(company_id, {'website_url': website})
        result = analyse_traffic(domain, months=months)
        visits = result.get('monthly_visits') if result.get('status') == 'completed' else None
        status = 'qualified' if visits is not None and float(visits) >= TRAFFIC_THRESHOLD else ('below_threshold' if visits is not None else 'pending')
        with get_db() as connection:
            connection.execute("UPDATE campaign_records SET monthly_visits=?, traffic_status=? WHERE campaign_id=? AND company_id=?", (visits, status, campaign_id, company_id))
        findings = dict(result)
        findings.update({'traffic_status': 'completed' if visits is not None else 'unavailable', 'research_status': 'completed' if visits is not None else 'unavailable', 'eligibility_status': status, 'threshold': TRAFFIC_THRESHOLD})
        add_research_record(company_id, 'traffic_analysis', 'TabAPI', findings, source_url=website)
        results.append({'company': item['source_brand_name'], 'domain': domain, 'monthly_visits': visits, 'traffic_status': status, 'credits_charged': result.get('credits_charged'), 'error': result.get('error')})
    return results


def score_campaign_leads(campaign_id):
    """Score every unique traffic-qualified company in a campaign."""
    with get_db() as connection:
        rows = connection.execute("SELECT DISTINCT company_id FROM campaign_records WHERE campaign_id=? AND company_id IS NOT NULL", (campaign_id,)).fetchall()
    results = []
    from database.campaign_research_queue import get_campaign_research_queue
    queue = {item["company_id"]: item for item in get_campaign_research_queue(campaign_id)}
    for row in rows:
        company_id = row["company_id"]
        try:
            entry = queue.get(company_id, {})
            if entry.get("traffic_status") != "qualified":
                results.append({"company_id": company_id, "qualification_status": "not_scored", "error": "Traffic is not qualified."})
                continue
            history = get_company_research_history(company_id)
            has_website_research = any(item.get("research_type") == "website_research" for item in history)
            if not has_website_research:
                run_company_research(
                    company_id=company_id,
                    mode="live",
                    monthly_visits_override=entry.get("monthly_visits"),
                    skip_traffic_api=True,
                )
            result = qualify_company(company_id, campaign_id=campaign_id)
            results.append(result)
        except Exception as error:
            results.append({"company_id": company_id, "qualification_status": "not_scored", "error": str(error)})
    return results


def get_campaign_intelligence(campaign_id):
    """Build a unified, current campaign dataframe from saved company and traffic records."""
    with get_db() as connection:
        rows = connection.execute(
            """SELECT cr.source_row_number, cr.source_brand_name AS company_name,
                      COALESCE(c.website_url, cr.website) AS website, cr.monthly_visits,
                      cr.traffic_status, c.qualification_score AS lead_score,
                      c.qualification_category AS lead_category, c.data_completeness,
                      c.id AS company_id
               FROM campaign_records cr JOIN companies c ON c.id=cr.company_id
               WHERE cr.campaign_id=? ORDER BY cr.source_row_number""",
            (campaign_id,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def build_campaign_report(campaign_id):
    """Create a multi-sheet Excel report from saved campaign intelligence."""
    data = get_campaign_intelligence(campaign_id)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        data.to_excel(writer, sheet_name='Campaign Overview', index=False)
        if not data.empty:
            data.sort_values('lead_score', ascending=False, na_position='last').to_excel(writer, sheet_name='Lead Prioritisation', index=False)
            data[['company_name', 'website', 'monthly_visits', 'traffic_status']].to_excel(writer, sheet_name='Website Intelligence', index=False)
        with get_db() as connection:
            contacts = connection.execute(
                "SELECT c.company_name, cc.contact_name, cc.designation, cc.email, cc.phone, cc.linkedin_url, cc.contact_source, cc.enrichment_status FROM company_contacts cc JOIN companies c ON c.id=cc.company_id JOIN campaign_records cr ON cr.company_id=c.id WHERE cr.campaign_id=? GROUP BY cc.id ORDER BY c.company_name",
                (campaign_id,),
            ).fetchall()
        pd.DataFrame([dict(row) for row in contacts]).to_excel(writer, sheet_name='Contact Intelligence', index=False)
    output.seek(0)
    return output.getvalue()
