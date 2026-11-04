
import json

from database.db import get_db


def add_research_record(
    company_id,
    research_type,
    source,
    findings,
    source_url=None,
    confidence="unverified"
):
    """Save a research activity for a company."""

    if not research_type:
        raise ValueError("Research type is required.")

    if isinstance(findings, dict):
        findings = json.dumps(findings, ensure_ascii=False)

    with get_db() as connection:

        cursor = connection.execute(
            """
            INSERT INTO research_history (
                company_id,
                research_type,
                source,
                source_url,
                findings,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                research_type,
                source,
                source_url,
                findings,
                confidence
            )
        )

        return cursor.lastrowid


def get_company_research_history(company_id):
    """Retrieve all research records for a company."""

    with get_db() as connection:

        records = connection.execute(
            """
            SELECT *
            FROM research_history
            WHERE company_id = ?
            ORDER BY researched_at DESC
            """,
            (company_id,)
        ).fetchall()

        results = []

        for record in records:

            item = dict(record)

            try:
                item["findings"] = json.loads(
                    item["findings"]
                )
            except (TypeError, json.JSONDecodeError):
                pass

            results.append(item)

        return results


def add_company_event(
    company_id,
    event_type,
    event_title,
    event_description=None,
    amount=None,
    currency=None,
    event_date=None,
    source_url=None,
    verification_status="unverified"
):
    """Save a funding, expansion or achievement event."""

    with get_db() as connection:

        cursor = connection.execute(
            """
            INSERT INTO company_events (
                company_id,
                event_type,
                event_title,
                event_description,
                amount,
                currency,
                event_date,
                source_url,
                verification_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                event_type,
                event_title,
                event_description,
                amount,
                currency,
                event_date,
                source_url,
                verification_status
            )
        )

        return cursor.lastrowid


def get_company_events(company_id):
    """Retrieve funding and growth events."""

    with get_db() as connection:

        records = connection.execute(
            """
            SELECT *
            FROM company_events
            WHERE company_id = ?
            ORDER BY created_at DESC
            """,
            (company_id,)
        ).fetchall()

        return [dict(record) for record in records]
