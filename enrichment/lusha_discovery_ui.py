from pathlib import Path
import json
import pandas as pd
import streamlit as st

from enrichment.lusha_prospecting import LushaProspectingClient
from database.contact_repository import add_contact


def _first_value(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        value = obj.get(key)
        if value not in (None, ''):
            return value
    return None


def _normalise_contact(item, company_name, domain):
    if not isinstance(item, dict):
        return None
    job = item.get('jobTitle') or item.get('job_title') or {}
    company = item.get('company') or {}
    socials = item.get('socialLinks') or item.get('social_links') or {}
    full_name = _first_value(item, 'fullName', 'full_name', 'name')
    if not full_name:
        full_name = ' '.join(str(x) for x in [item.get('firstName') or item.get('first_name') or '', item.get('lastName') or item.get('last_name') or '']).strip()
    if not full_name:
        return None
    title = job.get('title') if isinstance(job, dict) else job
    linkedin = _first_value(socials, 'linkedin', 'linkedinUrl', 'linkedin_url')
    linkedin = linkedin or _first_value(item, 'linkedinUrl', 'linkedin_url')
    contact_id = _first_value(item, 'id', 'contactId', 'contact_id')
    return {
        'lusha_contact_id': str(contact_id or ''),
        'contact_name': str(full_name),
        'designation': str(title or item.get('title') or ''),
        'company_name': str(_first_value(company, 'name', 'companyName') or company_name),
        'company_domain': str(_first_value(company, 'domain', 'website') or domain),
        'linkedin_url': str(linkedin or ''),
        'contact_source': 'Lusha Prospecting API',
        'enrichment_status': 'prospected',
        'revealed_emails': '',
        'revealed_phones': '',
    }


def _extract_contacts(response):
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return []
    for key in ('contacts', 'results', 'data', 'items'):
        value = response.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_contacts(value)
            if nested:
                return nested
    return []


def render_lusha_discovery_ui(output_path, company_id, company_name, website_url):
    st.subheader('Lusha Contact Discovery')
    st.caption('Search for relevant decision-makers. Prospecting may consume Lusha credits; contact details are not revealed by this search.')
    domain = str(website_url or '').strip().lower()
    if domain.startswith(('https://', 'http://')):
        domain = domain.split('://', 1)[1]
    domain = domain.split('/', 1)[0].split(':', 1)[0].strip()
    if domain.startswith('www.'):
        domain = domain[4:]
    if not domain:
        st.warning('Add the official company website before searching Lusha.')
        return
    roles = ['Operations Head', 'Head of Operations', 'VP Operations', 'Growth Head', 'Head of Growth', 'Supply Chain Head', 'Head of Supply Chain', 'Marketplace Head', 'D2C Head']
    selected_roles = st.multiselect(
        'Priority job titles (optional for domain-only test)',
        roles,
        default=roles,
        key=f'l_sha_roles_{company_id}',
        help='Clear all titles to search the selected company domain without a job-title filter.'
    )
    page_size = st.select_slider('Maximum prospects to request', options=[10, 25, 50], value=10, key=f'l_sha_size_{company_id}')
    confirm = st.checkbox('I approve a Lusha prospecting search for this company; it may consume credits.', key=f'l_sha_approve_{company_id}')
    if st.button('Search decision-makers in Lusha', type='primary', disabled=(not confirm), key=f'l_sha_search_{company_id}'):
        filters = {
            'companies': {'include': {'domains': [domain]}},
        }
        # Add a title filter only when the user selects titles. This allows
        # a controlled domain-only search to isolate company-domain coverage.
        if selected_roles:
            filters['contacts'] = {'include': {'jobTitles': selected_roles}}

        payload = {
            'pagination': {'page': 0, 'size': max(10, int(page_size))},
            'filters': filters,
            # Exclude-DNC filtering is not included in every Lusha plan.
            # Omit that optional flag so prospecting works on the current plan.
            'options': {'includePartialProfiles': True},
        }
        try:
            with st.spinner('Searching Lusha for matching decision-makers...'):
                with LushaProspectingClient() as client:
                    response = client.prospect_contacts(payload)
            raw_contacts = _extract_contacts(response)
            contacts = [_normalise_contact(item, company_name, domain) for item in raw_contacts]
            contacts = [item for item in contacts if item]
            if not contacts:
                st.warning('Lusha returned no usable contact records. Check API access, filters and response details below.')
                st.json(response)
                return
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            existing = pd.read_csv(output_path, dtype=str).fillna('') if output_path.exists() else pd.DataFrame()
            new_df = pd.DataFrame(contacts)
            combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
            if 'lusha_contact_id' in combined.columns:
                combined = combined.drop_duplicates(subset=['lusha_contact_id'], keep='last')
            combined.to_csv(output_path, index=False, encoding='utf-8-sig')
            saved = 0
            for contact in contacts:
                if not contact.get('contact_name'):
                    continue
                result = add_contact(company_id, {
                    'contact_name': contact['contact_name'],
                    'designation': contact['designation'],
                    'linkedin_url': contact['linkedin_url'],
                    'contact_source': 'Lusha Prospecting API',
                    'enrichment_status': 'prospected',
                })
                saved += int(bool(result.get('success')))
            st.success(f'Lusha returned {len(contacts)} contacts. {saved} new contact records saved to the company database.')
            st.dataframe(pd.DataFrame(contacts)[['contact_name', 'designation', 'company_name', 'linkedin_url']], use_container_width=True, hide_index=True)
            st.caption('Emails and phone numbers have not been revealed. Use the separate approved reveal workflow only when needed.')
            billing = response.get('billing') if isinstance(response, dict) else None
            if billing:
                st.write('Lusha search billing information')
                st.json(billing)
        except Exception as error:
            st.error(f'Lusha prospecting failed: {type(error).__name__}: {error}')
