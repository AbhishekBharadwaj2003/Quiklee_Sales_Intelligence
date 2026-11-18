import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from enrichment.lusha_prospecting import LushaProspectingClient
from database.db import get_db


FIELD_MAP = {
    "emails": "email",
    "phones": "phone",
}


def _row_value(row, key, index):
    return row.get(key) if isinstance(row, dict) else row[index]


def _clean(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_domain(value):
    value = _clean(value).lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0].split("?")[0].split("#")[0]
    return value.removeprefix("www.").rstrip(".")


def _brand_identity(contact):
    domain = _normalize_domain(contact.get("company_domain", ""))
    if domain:
        return domain

    name = _clean(contact.get("company_name", "")).lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    if not name:
        raise ValueError(
            "Cannot establish brand identity: company domain and name are missing."
        )
    return f"name:{name}"


def _extract_values(obj, field):
    found = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = str(key).lower()

            if field == "emails" and key_lower in ("email", "emails"):
                found.extend(
                    _extract_leaf_values(value, ("email", "address", "value"))
                )
            elif field == "phones" and key_lower in ("phone", "phones"):
                found.extend(
                    _extract_leaf_values(value, ("number", "phone", "value"))
                )
            elif isinstance(value, (dict, list)):
                found.extend(_extract_values(value, field))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(_extract_values(item, field))

    return list(dict.fromkeys(value for value in found if value))


def _extract_leaf_values(value, preferred_keys):
    values = []

    if isinstance(value, str):
        if value.strip():
            values.append(value.strip())
    elif isinstance(value, (int, float)):
        values.append(str(value))
    elif isinstance(value, dict):
        for key in preferred_keys:
            if key in value:
                values.extend(
                    _extract_leaf_values(value[key], preferred_keys)
                )
    elif isinstance(value, list):
        for item in value:
            values.extend(_extract_leaf_values(item, preferred_keys))

    return values


def _save_contacts(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _company_id_for_contact(connection, contact):
    domain = _normalize_domain(contact.get("company_domain", ""))
    if domain:
        rows = connection.execute(
            """
            SELECT id
            FROM companies
            WHERE lower(trim(domain)) IN (?, ?)
            """,
            (domain, f"www.{domain}"),
        ).fetchall()

        if len(rows) == 1:
            return _row_value(rows[0], "id", 0)

        # Fallback handles older company rows where website_url carries domain.
        all_rows = connection.execute(
            """
            SELECT id, domain, website_url
            FROM companies
            WHERE domain IS NOT NULL OR website_url IS NOT NULL
            """
        ).fetchall()
        matches = [
            _row_value(row, "id", 0) for row in all_rows
            if _normalize_domain(_row_value(row, "domain", 1) or _row_value(row, "website_url", 2)) == domain
        ]
        if len(matches) == 1:
            return matches[0]

    company_name = _clean(contact.get("company_name", ""))
    if company_name:
        rows = connection.execute(
            """
            SELECT id FROM companies
            WHERE lower(trim(company_name)) = lower(trim(?))
            """,
            (company_name,),
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0]

    return None


def _ensure_ledger_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_reveal_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_key TEXT NOT NULL,
            company_id INTEGER,
            field_type TEXT NOT NULL,
            reveal_status TEXT NOT NULL DEFAULT 'not_revealed',
            contact_id TEXT,
            revealed_value TEXT,
            credits_charged REAL DEFAULT 0,
            campaign_id INTEGER,
            attempted_at TIMESTAMP,
            revealed_at TIMESTAMP,
            error_details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reveal_ledger_brand_field
        ON contact_reveal_ledger(brand_key, field_type)
        """
    )


def _seed_historical_reveals(path):
    """
    Import already-recorded reveals from the contacts CSV into the ledger.
    This is idempotent and does not call Lusha.
    """
    if not path.exists():
        return 0

    df = pd.read_csv(path, dtype=str).fillna("")
    inserted = 0

    with get_db() as connection:
        _ensure_ledger_table(connection)

        for _, contact in df.iterrows():
            contact_id = _clean(contact.get("lusha_contact_id", ""))
            if not contact_id:
                continue

            brand_key = _brand_identity(contact)
            company_id = _company_id_for_contact(connection, contact)

            for plural_field, field_type in FIELD_MAP.items():
                value = _clean(contact.get(f"revealed_{plural_field}", ""))
                status = _clean(
                    contact.get(f"{plural_field}_reveal_status", "")
                ).lower()

                # A revealed value is definitive evidence of a prior reveal.
                # Prior ambiguous/failed attempts are also locked if the CSV
                # records them, to prevent an unsafe paid retry.
                if value:
                    ledger_status = "revealed"
                elif status in (
                    "request_in_progress",
                    "attempted_no_data",
                    "error_check_billing_before_retry",
                    "revealed",
                ):
                    ledger_status = status
                else:
                    continue

                exists = connection.execute(
                    """
                    SELECT id FROM contact_reveal_ledger
                    WHERE brand_key = ? AND field_type = ? AND contact_id = ?
                    LIMIT 1
                    """,
                    (brand_key, field_type, contact_id),
                ).fetchone()

                if exists:
                    continue

                attempted_at = _clean(
                    contact.get(
                        f"{plural_field}_reveal_attempted_at", ""
                    )
                ) or None
                revealed_at = _clean(
                    contact.get(f"{plural_field}_reveal_response_at", "")
                ) or None
                credits_raw = _clean(
                    contact.get(
                        f"{plural_field}_reveal_credits_charged", "0"
                    )
                )
                try:
                    credits = float(credits_raw) if credits_raw else 0
                except ValueError:
                    credits = 0

                connection.execute(
                    """
                    INSERT INTO contact_reveal_ledger (
                        brand_key, company_id, field_type, reveal_status,
                        contact_id, revealed_value, credits_charged,
                        attempted_at, revealed_at, error_details,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        brand_key,
                        company_id,
                        field_type,
                        ledger_status,
                        contact_id,
                        value or None,
                        credits,
                        attempted_at,
                        revealed_at,
                        _clean(
                            contact.get(f"{plural_field}_reveal_error", "")
                        ) or None,
                    ),
                )
                inserted += 1

    return inserted


def _reserve_brand_field(path, contact_id, field):
    """
    Atomically reserve a brand+field before the paid request.
    Any prior attempt for that brand+field blocks another reveal.
    """
    if field not in FIELD_MAP:
        raise ValueError("Unsupported reveal field.")

    df = pd.read_csv(path, dtype=str).fillna("")
    matches = df.index[df["lusha_contact_id"] == contact_id]
    if len(matches) != 1:
        raise ValueError("Contact ID was not found uniquely in the CSV.")

    contact = df.loc[matches[0]].to_dict()
    brand_key = _brand_identity(contact)
    field_type = FIELD_MAP[field]
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as connection:
        connection.execute("BEGIN")
        _ensure_ledger_table(connection)

        existing = connection.execute(
            """
            SELECT reveal_status, contact_id, attempted_at
            FROM contact_reveal_ledger
            WHERE brand_key = ? AND field_type = ? AND contact_id = ?
            ORDER BY id
            LIMIT 1
            """,
            (brand_key, field_type, contact_id),
        ).fetchone()

        if existing:
            status, prior_contact, attempted_at = (_row_value(existing, "reveal_status", 0), _row_value(existing, "contact_id", 1), _row_value(existing, "attempted_at", 2))
            raise ValueError(
                f"{field_type.title()} reveal is locked for brand "
                f"'{brand_key}'. Existing status: {status}; "
                f"contact: {prior_contact or 'unknown'}; "
                f"attempted: {attempted_at or 'unknown'}. "
                "Do not retry without manually reconciling Lusha billing "
                "and the ledger."
            )

        company_id = _company_id_for_contact(connection, contact)

        connection.execute(
            """
            INSERT INTO contact_reveal_ledger (
                brand_key, company_id, field_type, reveal_status,
                contact_id, credits_charged, attempted_at,
                updated_at
            )
            VALUES (?, ?, ?, 'request_in_progress', ?, 0, ?, CURRENT_TIMESTAMP)
            """,
            (
                brand_key,
                company_id,
                field_type,
                contact_id,
                now,
            ),
        )

    return df, matches[0], brand_key, field_type, now


def _update_ledger(
    brand_key,
    field_type,
    contact_id,
    status,
    values=None,
    credits=0,
    error=None,
):
    now = datetime.now(timezone.utc).isoformat()
    revealed_value = "; ".join(values or []) or None
    revealed_at = now if values else None

    with get_db() as connection:
        connection.execute(
            """
            UPDATE contact_reveal_ledger
            SET reveal_status = ?,
                revealed_value = COALESCE(?, revealed_value),
                credits_charged = ?,
                revealed_at = COALESCE(?, revealed_at),
                error_details = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE brand_key = ?
              AND field_type = ?
              AND contact_id = ?
            """,
            (
                status,
                revealed_value,
                credits,
                revealed_at,
                (str(error)[:500] if error else None),
                brand_key,
                field_type,
                contact_id,
            ),
        )


def _sync_revealed_value_to_database(contact, field, values):
    """
    Sync a successfully revealed email/phone into company_contacts.
    Campaign Excel reports read contact details from this table.
    """
    if not values:
        return 0

    company_id = None
    with get_db() as connection:
        company_id = _company_id_for_contact(connection, contact)

        if company_id is None:
            return 0

        linkedin = _clean(contact.get("linkedin_url"))
        name = _clean(contact.get("full_name")) or _clean(
            contact.get("contact_name")
        )
        column = "email" if field == "emails" else "phone"
        value = "; ".join(values)

        if linkedin:
            cursor = connection.execute(
                f"""
                UPDATE company_contacts
                SET {column} = ?, enrichment_status = 'revealed'
                WHERE company_id = ? AND linkedin_url = ?
                """,
                (value, company_id, linkedin),
            )
        else:
            cursor = connection.execute(
                f"""
                UPDATE company_contacts
                SET {column} = ?, enrichment_status = 'revealed'
                WHERE company_id = ? AND lower(trim(contact_name)) = lower(trim(?))
                """,
                (value, company_id, name),
            )

        return cursor.rowcount


def _reveal_one(path, contact_id, field, timeout=45):
    # Seed known historical reveals before attempting a new request.
    _seed_historical_reveals(path)

    df, index, brand_key, field_type, attempted_at = (
        _reserve_brand_field(path, contact_id, field)
    )

    status_column = f"{field}_reveal_status"
    value_column = f"revealed_{field}"
    df.at[index, status_column] = "request_in_progress"
    df.at[index, f"{field}_reveal_attempted_at"] = attempted_at
    _save_contacts(df, path)

    try:
        with LushaProspectingClient(timeout=timeout) as client:
            response = client.reveal_contacts([contact_id], field)

        if not isinstance(response, dict):
            raise RuntimeError("Unexpected response format from Lusha.")

        results = response.get("results", [])
        contact_result = results[0] if results else response
        values = _extract_values(contact_result, field)

        billing = response.get("billing", {})
        credits = billing.get("creditsCharged", 0)
        try:
            numeric_credits = float(credits or 0)
        except (TypeError, ValueError):
            numeric_credits = 0

        df = pd.read_csv(path, dtype=str).fillna("")
        matches = df.index[df["lusha_contact_id"] == contact_id]
        if len(matches) != 1:
            raise ValueError("Contact record disappeared during reveal.")

        index = matches[0]
        df.at[index, value_column] = "; ".join(values)
        df.at[index, status_column] = (
            "revealed" if values else "attempted_no_data"
        )
        df.at[index, f"{field}_reveal_credits_charged"] = str(credits)
        df.at[index, f"{field}_reveal_response_at"] = (
            datetime.now(timezone.utc).isoformat()
        )
        _save_contacts(df, path)

        ledger_status = "revealed" if values else "attempted_no_data"
        _update_ledger(
            brand_key,
            field_type,
            contact_id,
            ledger_status,
            values=values,
            credits=numeric_credits,
        )

        if values:
            _sync_revealed_value_to_database(
                df.loc[index].to_dict(), field, values
            )

        return values, credits

    except Exception as exc:
        # Keep the brand+field locked after an uncertain outcome. A failed
        # request may still have reached Lusha or consumed credits.
        try:
            df = pd.read_csv(path, dtype=str).fillna("")
            matches = df.index[df["lusha_contact_id"] == contact_id]
            if len(matches) == 1:
                index = matches[0]
                df.at[index, status_column] = (
                    "error_check_billing_before_retry"
                )
                df.at[index, f"{field}_reveal_error"] = str(exc)[:500]
                _save_contacts(df, path)
        finally:
            _update_ledger(
                brand_key,
                field_type,
                contact_id,
                "error_check_billing_before_retry",
                error=exc,
            )
        raise


def render_lusha_reveal_ui(csv_path, company_id=None, company_domain=None, company_name=None):
    path = Path(csv_path)

    st.subheader("Lusha Contact Reveal")
    st.caption(
        "Select one discovered contact. Email and phone are separate paid "
        "operations and each requires its own approval. To avoid accidental "
        "repeat charges, the current safety ledger locks each field once per brand."
    )

    if not path.exists():
        st.warning("Lusha contacts CSV was not found.")
        return

    try:
        seeded = _seed_historical_reveals(path)
        if seeded:
            st.info(
                f"Imported {seeded} historical reveal record(s) "
                "into the brand-level ledger."
            )
    except Exception as exc:
        st.error(f"Could not reconcile historical reveals: {exc}")
        return

    df = pd.read_csv(path, dtype=str).fillna("")
    if df.empty:
        st.info("No discovered Lusha contacts are available.")
        return

    # Support both the discovery schema (contact_name) and the older
    # reveal schema (full_name) so existing saved contacts remain usable.
    if "full_name" not in df.columns:
        df["full_name"] = ""
    if "contact_name" not in df.columns:
        df["contact_name"] = ""
    df["full_name"] = df["full_name"].replace("", pd.NA).fillna(
        df["contact_name"]
    ).fillna("")
    df["contact_name"] = df["contact_name"].replace("", pd.NA).fillna(
        df["full_name"]
    ).fillna("")

    if "lusha_contact_id" not in df.columns:
        st.error(
            "The contacts file has no Lusha contact IDs. "
            "These records cannot be used for Lusha reveal requests."
        )
        return

    df["lusha_contact_id"] = df["lusha_contact_id"].fillna("").astype(str).str.strip()
    eligible = df[
        (df["lusha_contact_id"] != "")
        & (
            df.get("full_name", pd.Series("", index=df.index)).astype(str).str.strip() != ""
        )
    ].copy()

    # The contacts CSV is shared across all brands. Restrict the reveal picker
    # to the currently selected company, preferring the persisted company_id.
    if company_id is not None:
        selected_id = str(company_id).strip()
        company_mask = pd.Series(False, index=eligible.index)

        if "company_id" in eligible.columns:
            company_mask |= eligible["company_id"].astype(str).str.strip() == selected_id

        selected_domain = _normalize_domain(company_domain)
        if selected_domain and "company_domain" in eligible.columns:
            company_mask |= eligible["company_domain"].map(_normalize_domain) == selected_domain

        if not company_mask.any() and company_name and "company_name" in eligible.columns:
            company_mask = (
                eligible["company_name"].astype(str).str.strip().str.casefold()
                == str(company_name).strip().casefold()
            )

        eligible = eligible[company_mask].copy()

    if eligible.empty:
        st.warning(
            "No discovered contacts have both a name and a Lusha contact ID. "
            "Contact discovery results may still be useful for outreach, but "
            "Lusha's reveal endpoint requires a contact ID."
        )
        return

    eligible["_row_index"] = eligible.index
    eligible["_label"] = eligible.apply(
        lambda row: (
            str(row.get("full_name") or row.get("contact_name") or "Unnamed")
            + " — "
            + str(row.get("designation") or "Title unavailable")
            + " — "
            + str(row.get("company_name") or "Company unavailable")
        ),
        axis=1,
    )

    selected_row_index = st.selectbox(
        "Select one contact to enrich",
        options=eligible["_row_index"].tolist(),
        format_func=lambda row_index: eligible.loc[
            eligible["_row_index"] == row_index, "_label"
        ].iloc[0],
        key=f"lusha_reveal_contact_selection_{company_id or 'all'}",
    )
    contact = df.loc[selected_row_index].to_dict()
    contact_id = _clean(contact.get("lusha_contact_id"))
    name = _clean(contact.get("full_name")) or _clean(contact.get("contact_name"))
    company = _clean(contact.get("company_name"))
    brand_key = _brand_identity(contact)

    st.write(f"**{name}**")
    st.write(f"{contact.get('designation') or 'Designation unavailable'} · {company}")
    if _clean(contact.get("linkedin_url")):
        st.write(_clean(contact.get("linkedin_url")))

    for field, label in [
        ("emails", "Email"),
        ("phones", "Phone"),
    ]:
        field_type = FIELD_MAP[field]
        availability_value = _clean(
            contact.get(f"{field[:-1]}_reveal_available", "")
        ).lower()
        value_column = f"revealed_{field}"
        status_column = f"{field}_reveal_status"
        existing_value = _clean(contact.get(value_column))
        existing_status = _clean(contact.get(status_column))

        with get_db() as connection:
            ledger = connection.execute(
                """
                SELECT reveal_status, contact_id, revealed_value
                FROM contact_reveal_ledger
                WHERE brand_key = ? AND field_type = ?
                ORDER BY id
                LIMIT 1
                """,
                (brand_key, field_type),
            ).fetchone()

        st.divider()
        st.markdown(f"**{label}**")

        if existing_value:
            st.success(f"{label} already revealed: {existing_value}")
            continue

        if ledger:
            ledger_status, ledger_contact, ledger_value = ledger
            if ledger_value:
                st.success(
                    f"{label} already revealed for this brand "
                    f"(contact ID: {ledger_contact or 'unknown'})."
                )
            else:
                st.warning(
                    f"{label} reveal is locked for this brand. "
                    f"Ledger status: {ledger_status}. "
                    "Check Lusha billing and reconcile the ledger before "
                    "attempting another request."
                )
            continue

        if existing_status:
            st.warning(
                f"{label}: {existing_status}. "
                "A previous attempt is recorded; do not retry until billing "
                "has been checked."
            )
            continue

        if availability_value in ("false", "no", "unavailable", "not_available"):
            st.info(f"{label} is marked unavailable by Lusha.")
            continue

        credits = _clean(
            contact.get(f"{field[:-1]}_reveal_credits", "")
        ) or "Unknown"

        if availability_value in ("true", "yes", "available"):
            st.caption(f"Lusha indicates this field is available. Estimated cost: {credits} credit(s).")
        else:
            st.warning(
                f"Lusha did not provide availability metadata for this {label.lower()}. "
                "A reveal request may return no data and may consume credits."
            )
            st.caption(f"Estimated cost: {credits} credit(s).")

        approved = st.checkbox(
            f"I approve one {label.lower()} reveal for {name}. "
            f"Potential cost: {credits} credit(s).",
            key=f"approve_{field}_{contact_id}",
        )

        if st.button(
            f"Reveal {label} for {name}",
            key=f"reveal_{field}_{contact_id}",
            disabled=not approved,
            use_container_width=True,
        ):
            try:
                with st.spinner(f"Revealing {label.lower()}..."):
                    values, actual_credits = _reveal_one(
                        path, contact_id, field
                    )

                if values:
                    st.success(
                        f"{label} revealed. Credits charged: {actual_credits}"
                    )
                else:
                    st.warning(
                        f"No {label.lower()} data returned. "
                        f"Credits charged: {actual_credits}. "
                        "This brand+field is now locked to prevent repeat charges."
                    )
                st.rerun()

            except Exception as exc:
                st.error(str(exc))
