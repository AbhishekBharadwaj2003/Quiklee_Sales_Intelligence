from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from enrichment.lusha_prospecting import LushaProspectingClient
from database.contact_repository import add_contact


ROLE_PRIORITY = {
    "Operations": 1,
    "Growth": 2,
    "Supply Chain": 3,
    "Marketplace / D2C": 4,
    "Founder / Executive": 5,
    "Other": 6,
}

ROLE_SCORES = {
    "Operations": 100,
    "Growth": 90,
    "Supply Chain": 80,
    "Marketplace / D2C": 70,
    "Founder / Executive": 60,
    "Other": 20,
}


def _first_value(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalise_domain(website_url):
    domain = str(website_url or "").strip().lower()
    if domain.startswith(("https://", "http://")):
        domain = domain.split("://", 1)[1]
    domain = domain.split("/", 1)[0].split(":", 1)[0].strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _normalise_contact(item, company_name, domain):
    if not isinstance(item, dict):
        return None

    job = item.get("jobTitle") or item.get("job_title") or {}
    company = item.get("company") or {}
    socials = item.get("socialLinks") or item.get("social_links") or {}

    full_name = _first_value(item, "fullName", "full_name", "name")
    if not full_name:
        first_name = item.get("firstName") or item.get("first_name") or ""
        last_name = item.get("lastName") or item.get("last_name") or ""
        full_name = " ".join(str(part) for part in (first_name, last_name) if part).strip()
    if not full_name:
        return None

    title = job.get("title") if isinstance(job, dict) else job
    linkedin = _first_value(socials, "linkedin", "linkedinUrl", "linkedin_url")
    linkedin = linkedin or _first_value(item, "linkedinUrl", "linkedin_url")
    contact_id = _first_value(
        item, "id", "contactId", "contact_id", "personId", "person_id"
    )

    # Preserve availability/cost metadata when Lusha includes it. If the
    # prospecting response omits these fields, mark availability as unknown
    # rather than assuming a paid reveal is available.
    email_available = _first_value(
        item, "emailRevealAvailable", "email_reveal_available",
        "hasEmail", "has_email"
    )
    phone_available = _first_value(
        item, "phoneRevealAvailable", "phone_reveal_available",
        "hasPhone", "has_phone"
    )
    email_cost = _first_value(
        item, "emailRevealCredits", "email_reveal_credits",
        "emailCredits", "email_credits"
    )
    phone_cost = _first_value(
        item, "phoneRevealCredits", "phone_reveal_credits",
        "phoneCredits", "phone_credits"
    )

    return {
        "lusha_contact_id": str(contact_id or ""),
        "contact_name": str(full_name).strip(),
        "full_name": str(full_name).strip(),
        "designation": str(title or item.get("title") or "").strip(),
        "company_name": str(_first_value(company, "name", "companyName") or company_name),
        "company_domain": str(_first_value(company, "domain", "website") or domain),
        "linkedin_url": str(linkedin or "").strip(),
        "email_reveal_available": (
            str(email_available).lower()
            if email_available is not None else "unknown"
        ),
        "phone_reveal_available": (
            str(phone_available).lower()
            if phone_available is not None else "unknown"
        ),
        "email_reveal_credits": str(email_cost or ""),
        "phone_reveal_credits": str(phone_cost or ""),
        "revealed_emails": "",
        "revealed_phones": "",
        "contact_source": "Lusha Prospecting API",
        "enrichment_status": "prospected",
        "lusha_raw_contact_json": json.dumps(
            item, ensure_ascii=False, default=str
        ),
    }


def _classify_contact(designation):
    """Rank discovered people against Quiklee's agreed prospecting priorities."""
    title = str(designation or "").lower()
    compact = title.replace("-", " ").replace("/", " ")

    if any(term in compact for term in ("operations", "operational", "ops ")):
        bucket = "Operations"
    elif "growth" in compact:
        bucket = "Growth"
    elif any(term in compact for term in ("supply chain", "logistics", "fulfillment", "fulfilment")):
        bucket = "Supply Chain"
    elif any(term in compact for term in (
        "marketplace", "ecommerce", "e commerce", "e-commerce", "d2c",
        "direct to consumer", "digital commerce", "online business"
    )):
        bucket = "Marketplace / D2C"
    elif any(term in compact for term in (
        "founder", "co founder", "co-founder", "chief executive", " ceo",
        "managing director", "owner", "president"
    )):
        bucket = "Founder / Executive"
    else:
        bucket = "Other"

    score = ROLE_SCORES[bucket]
    return bucket, ROLE_PRIORITY[bucket], score


def _rank_contacts(contacts):
    ranked = []
    for contact in contacts:
        item = dict(contact)
        bucket, priority, score = _classify_contact(item.get("designation"))
        item["role_category"] = bucket
        item["priority_order"] = priority
        item["relevance_score"] = score
        item["recommended_for_outreach"] = bucket != "Other"
        ranked.append(item)

    return sorted(
        ranked,
        key=lambda item: (
            item["priority_order"],
            str(item.get("designation") or "").lower(),
            str(item.get("contact_name") or "").lower(),
        ),
    )


def _contact_identity(contact):
    contact_id = str(contact.get("lusha_contact_id") or "").strip()
    if contact_id:
        return "id:" + contact_id

    linkedin = str(contact.get("linkedin_url") or "").strip().lower()
    if linkedin:
        return "linkedin:" + linkedin.rstrip("/")

    name = str(contact.get("contact_name") or "").strip().lower()
    designation = str(contact.get("designation") or "").strip().lower()
    company = str(contact.get("company_name") or "").strip().lower()
    return "fallback:" + "|".join((name, designation, company))


def _extract_contacts(response):
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return []

    for key in ("contacts", "results", "data", "items"):
        value = response.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_contacts(value)
            if nested:
                return nested
    return []


def _save_raw_response(output_path, payload, response, company_id, company_name, domain):
    """Append the unmodified prospecting response for audit/debugging."""
    output_path = Path(output_path)
    raw_path = output_path.with_name("lusha_raw_responses.jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "company_id": company_id,
        "company_name": company_name,
        "domain": domain,
        "request_payload": payload,
        "response": response,
    }
    with raw_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return raw_path


def render_lusha_discovery_ui(output_path, company_id, company_name, website_url):
    st.subheader("Lusha Contact Discovery")
    st.caption(
        "Search by company domain, then rank every returned prospect against "
        "Quiklee's preferred decision-maker roles. Contact details are not revealed."
    )

    domain = _normalise_domain(website_url)
    if not domain:
        st.warning("Add the official company website before searching Lusha.")
        return

    roles = [
        "Operations Head",
        "Head of Operations",
        "VP Operations",
        "Growth Head",
        "Head of Growth",
        "Supply Chain Head",
        "Head of Supply Chain",
        "Marketplace Head",
        "D2C Head",
    ]
    selected_roles = st.multiselect(
        "Optional job-title filter",
        roles,
        default=[],
        key=f"lusha_roles_{company_id}",
        help=(
            "Leave this empty to search the company domain broadly. "
            "Quiklee will rank the returned contacts locally by role."
        ),
    )
    page_size = st.select_slider(
        "Maximum prospects to request",
        options=[10, 25, 50],
        value=10,
        key=f"lusha_size_{company_id}",
    )
    confirm = st.checkbox(
        "I approve a Lusha prospecting search for this company; it may consume credits.",
        key=f"lusha_approve_{company_id}",
    )

    if st.button(
        "Search decision-makers in Lusha",
        type="primary",
        disabled=not confirm,
        key=f"lusha_search_{company_id}",
    ):
        filters = {"companies": {"include": {"domains": [domain]}}}
        if selected_roles:
            filters["contacts"] = {"include": {"jobTitles": selected_roles}}

        payload = {
            "pagination": {"page": 0, "size": int(page_size)},
            "filters": filters,
            "options": {"includePartialProfiles": True},
        }

        try:
            with st.spinner("Searching Lusha for matching prospects..."):
                with LushaProspectingClient() as client:
                    response = client.prospect_contacts(payload)

            raw_path = _save_raw_response(
                output_path, payload, response, company_id, company_name, domain
            )

            raw_contacts = _extract_contacts(response)
            contacts = [
                _normalise_contact(item, company_name, domain)
                for item in raw_contacts
            ]
            contacts = [item for item in contacts if item]

            # Persist the owning company ID with every discovered contact.
            # The shared CSV contains multiple brands, so this key is essential
            # for isolating each company's contacts in the UI and reports.
            for contact in contacts:
                contact["company_id"] = str(company_id)

            if not contacts:
                st.warning(
                    "Lusha returned no usable contact records. "
                    "The raw response has been archived for troubleshooting."
                )
                st.json(response)
                st.caption(f"Raw response archive: {raw_path.name}")
                return

            ranked_contacts = _rank_contacts(contacts)

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            existing = (
                pd.read_csv(output_path, dtype=str).fillna("")
                if output_path.exists()
                else pd.DataFrame()
            )

            new_df = pd.DataFrame(ranked_contacts)
            combined = (
                pd.concat([existing, new_df], ignore_index=True, sort=False)
                if not existing.empty
                else new_df
            )

            # Preserve every distinct contact. Never collapse all blank Lusha IDs
            # into one row; fall back to LinkedIn URL or name/title/company.
            if not combined.empty:
                combined["_identity"] = combined.apply(
                    lambda row: _contact_identity(row.to_dict()), axis=1
                )
                combined = combined.drop_duplicates(
                    subset=["_identity"], keep="last"
                ).drop(columns=["_identity"])

                # Recalculate ranking for older CSV rows as well.
                old_ranked = _rank_contacts(combined.to_dict("records"))
                combined = pd.DataFrame(old_ranked)

            combined.to_csv(output_path, index=False, encoding="utf-8-sig")

            saved = 0
            already_present = 0
            for contact in ranked_contacts:
                result = add_contact(
                    company_id,
                    {
                        "contact_name": contact["contact_name"],
                        "designation": contact["designation"],
                        "linkedin_url": contact["linkedin_url"],
                        "contact_source": "Lusha Prospecting API",
                        "enrichment_status": "prospected",
                    },
                )
                if result.get("success"):
                    saved += 1
                else:
                    already_present += 1

            display_columns = [
                "contact_name",
                "designation",
                "role_category",
                "relevance_score",
                "recommended_for_outreach",
                "company_name",
                "linkedin_url",
            ]
            display_df = pd.DataFrame(ranked_contacts)
            st.success(
                f"Lusha returned {len(ranked_contacts)} contacts. "
                f"{saved} new database records saved; "
                f"{already_present} were already present."
            )

            counts = (
                display_df["role_category"]
                .value_counts()
                .reindex(list(ROLE_PRIORITY.keys()), fill_value=0)
            )
            st.write("**Role relevance breakdown**")
            st.dataframe(
                counts.rename_axis("role_category").reset_index(name="contacts"),
                use_container_width=True,
                hide_index=True,
            )

            st.write("**Contacts ranked for Quiklee outreach**")
            st.dataframe(
                display_df[display_columns],
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "All returned contacts are retained in the CSV and company database. "
                "Recommended-for-outreach is a ranking aid, not proof of decision authority."
            )
            st.caption(
                f"Unmodified API response archived as {raw_path.name}. "
                "Emails and phone numbers have not been revealed."
            )

            billing = response.get("billing") if isinstance(response, dict) else None
            if billing:
                st.write("Lusha search billing information")
                st.json(billing)

        except Exception as error:
            st.error(f"Lusha prospecting failed: {type(error).__name__}: {error}")


def render_lusha_bulk_discovery_ui(output_path, companies, batch_label):
    """One-click prospecting + email reveal waterfall, one final contact per brand."""
    st.subheader("Bulk Contact Discovery + Email Reveal")
    st.caption(
        "For each brand, search Operations → Growth → Supply Chain → Marketplace/D2C. "
        "Reveal the candidate's email immediately; if no email is returned, move to the next role."
    )
    st.write(f"Dataset: **{batch_label}** · Brands: **{len(companies)}**")
    approved = st.checkbox(
        "I approve automated prospecting and email-reveal requests for this dataset. "
        "Multiple attempts per brand may consume Lusha credits.",
        key=f"pq_bulk_approve_{batch_label}",
    )
    run_all = st.button(
        "Find contact + reveal email for every brand",
        type="primary",
        disabled=not approved or not companies,
        key=f"pq_bulk_run_all_{batch_label}",
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    priority_queries = [
        ("Operations", ["Operations Head", "Head of Operations", "VP Operations", "Director of Operations"]),
        ("Growth", ["Growth Head", "Head of Growth", "VP Growth", "Director of Growth"]),
        ("Supply Chain", ["Supply Chain Head", "Head of Supply Chain", "VP Supply Chain", "Director Supply Chain"]),
        ("Marketplace / D2C", ["Marketplace Head", "D2C Head", "Head of Marketplace", "Head of D2C"]),
    ]

    if run_all:
        from enrichment.lusha_reveal_ui import _reveal_one

        progress = st.progress(0)
        status = st.empty()
        final_rows = []
        no_email_count = 0
        saved_count = 0

        for brand_idx, company in enumerate(companies):
            brand_name = str(company.get("company_name") or "").strip()
            domain = _normalise_domain(company.get("website_url"))
            status.text(f"{brand_idx + 1}/{len(companies)} — {brand_name}")
            final = None
            last_candidate = None
            stop_on_error = False

            if not domain:
                final_rows.append({
                    "brand": brand_name, "contact": "", "designation": "",
                    "email": "", "phone": "", "LinkedIn": "", "status": "Skipped — missing website/domain",
                })
                progress.progress((brand_idx + 1) / len(companies))
                continue

            for category, titles in priority_queries:
                payload = {
                    "pagination": {"page": 0, "size": 10},
                    "filters": {
                        "companies": {"include": {"domains": [domain]}},
                        "contacts": {"include": {"jobTitles": titles}},
                    },
                    "options": {"includePartialProfiles": True},
                }
                try:
                    with LushaProspectingClient() as client:
                        response = client.prospect_contacts(payload)
                except Exception as search_error:
                    final = {
                        "brand": brand_name, "contact": "", "designation": "",
                        "email": "", "phone": "", "LinkedIn": "",
                        "status": f"Prospecting error in {category}: {type(search_error).__name__}",
                    }
                    stop_on_error = True
                    break

                normalized = [
                    _normalise_contact(item, brand_name, domain)
                    for item in _extract_contacts(response)
                ]
                ranked = [
                    item for item in _rank_contacts([x for x in normalized if x])
                    if item.get("role_category") == category
                ]
                # Reveal one best-ranked candidate in this category before falling
                # back to the next category. Do not fan out reveal requests.
                if not ranked:
                    continue
                candidate = ranked[0]
                candidate["company_id"] = str(company.get("id", ""))
                candidate["bulk_selection_priority"] = category
                candidate["bulk_dataset"] = batch_label
                last_candidate = candidate

                # Persist the candidate first: the reveal safety ledger requires
                # a unique contact-ID row in the CSV.
                current = pd.read_csv(output_path, dtype=str).fillna("") if output_path.exists() else pd.DataFrame()
                if not current.empty:
                    current = current.astype(object)
                identity = _contact_identity(candidate)
                if not current.empty:
                    identities = current.apply(lambda row: _contact_identity(row.to_dict()), axis=1)
                    match_indices = current.index[identities == identity].tolist()
                else:
                    match_indices = []
                if match_indices:
                    row_idx = match_indices[-1]
                    for key, value in candidate.items():
                        if key not in current.columns:
                            current[key] = ""
                        current.at[row_idx, key] = value
                else:
                    current = pd.concat([current, pd.DataFrame([candidate])], ignore_index=True, sort=False)
                current.to_csv(output_path, index=False, encoding="utf-8-sig")

                contact_id = str(candidate.get("lusha_contact_id") or "").strip()
                if not contact_id:
                    # Without a Lusha contact ID, reveal cannot be attempted.
                    final = {
                        "brand": brand_name, "contact": candidate["contact_name"],
                        "designation": candidate["designation"], "email": "",
                        "LinkedIn": candidate.get("linkedin_url", ""),
                        "status": f"{category}: contact ID unavailable; moving to next priority",
                    }
                    continue

                prior_email = str(candidate.get("revealed_emails") or "").strip()
                prior_email_status = str(candidate.get("emails_reveal_status") or "").strip()
                prior_phone = str(candidate.get("revealed_phones") or "").strip()
                prior_phone_status = str(candidate.get("phones_reveal_status") or "").strip()

                if prior_email:
                    emails = [prior_email]
                    email_credits = 0
                elif prior_email_status:
                    final = {
                        "brand": brand_name, "contact": candidate["contact_name"],
                        "designation": candidate["designation"], "email": "",
                        "phone": prior_phone, "LinkedIn": candidate.get("linkedin_url", ""),
                        "status": f"Email reveal already attempted/locked ({category}); fallback skipped for safety",
                    }
                    stop_on_error = True
                    break
                else:
                    try:
                        emails, email_credits = _reveal_one(output_path, contact_id, "emails")
                    except Exception:
                        final = {
                            "brand": brand_name, "contact": candidate["contact_name"],
                            "designation": candidate["designation"], "email": "",
                            "phone": prior_phone, "LinkedIn": candidate.get("linkedin_url", ""),
                            "status": f"Email reveal uncertain/error ({category}); stopped to avoid duplicate charge",
                        }
                        stop_on_error = True
                        break

                if emails:
                    phone_values = [prior_phone] if prior_phone else []
                    phone_credits = 0
                    if not phone_values and not prior_phone_status:
                        try:
                            phone_values, phone_credits = _reveal_one(output_path, contact_id, "phones")
                        except Exception:
                            phone_values = []
                    final = {
                        "brand": brand_name, "contact": candidate["contact_name"],
                        "designation": candidate["designation"], "email": "; ".join(emails),
                        "phone": "; ".join(phone_values or []),
                        "LinkedIn": candidate.get("linkedin_url", ""),
                        "status": f"Email found — {category} (email {email_credits} + phone {phone_credits} credits)",
                    }
                    try:
                        add_contact(company.get("id"), {
                            "contact_name": candidate.get("contact_name", ""),
                            "designation": candidate.get("designation", ""),
                            "linkedin_url": candidate.get("linkedin_url", ""),
                            "contact_source": "Lusha Bulk Waterfall Prospecting + Email/Phone Reveal",
                            "enrichment_status": "revealed",
                        })
                    except Exception:
                        pass
                    saved_count += 1
                    break

                final = {
                    "brand": brand_name, "contact": candidate["contact_name"],
                    "designation": candidate["designation"], "email": "",
                    "phone": prior_phone, "LinkedIn": candidate.get("linkedin_url", ""),
                    "status": f"No email — tried {category} ({email_credits} credits); checking next priority",
                }

            if final is None and last_candidate:
                final = {
                    "brand": brand_name, "contact": last_candidate["contact_name"],
                    "designation": last_candidate["designation"], "email": "",
                    "phone": str(last_candidate.get("revealed_phones") or ""), "LinkedIn": last_candidate.get("linkedin_url", ""),
                    "status": "All priority categories exhausted; no email found",
                }
            if final is None:
                final = {
                    "brand": brand_name, "contact": "", "designation": "",
                    "email": "", "phone": "", "LinkedIn": "", "status": "No matching contact found",
                }
            if not final.get("email"):
                no_email_count += 1
            final_rows.append(final)
            progress.progress((brand_idx + 1) / len(companies))

        status.empty()
        progress.empty()
        st.success(
            f"Automated waterfall completed. {saved_count} brands returned email addresses; "
            f"{no_email_count} did not."
        )
        if final_rows:
            result_df = pd.DataFrame(final_rows)
            for column in ("brand", "contact", "designation", "email", "phone", "LinkedIn", "status"):
                if column not in result_df.columns:
                    result_df[column] = ""
            st.dataframe(result_df[["brand", "contact", "designation", "email", "phone", "LinkedIn", "status"]], use_container_width=True, hide_index=True)

    # Always render saved results on Streamlit reruns, independent of the action button.
    if output_path.exists():
        saved_contacts_df = pd.read_csv(output_path, dtype=str).fillna("")
        dataset_contacts = saved_contacts_df[
            saved_contacts_df.get("bulk_dataset", pd.Series("", index=saved_contacts_df.index)).astype(str)
            == str(batch_label)
        ].copy()
        if not dataset_contacts.empty:
            for column in ("company_name", "contact_name", "designation", "revealed_emails", "revealed_phones", "linkedin_url"):
                if column not in dataset_contacts.columns:
                    dataset_contacts[column] = ""
            st.write("**Contacts, emails and phones saved for this dataset**")
            st.dataframe(
                dataset_contacts[["company_name", "contact_name", "designation", "revealed_emails", "revealed_phones", "linkedin_url"]],
                use_container_width=True,
                hide_index=True,
            )
    st.caption("Phone reveal is attempted for the selected contact after an email is found; phone reveal errors do not trigger another designation search.")
