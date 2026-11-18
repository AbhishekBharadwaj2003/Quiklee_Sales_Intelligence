
import os
import requests

from config.settings import LUSHA_API_KEY

BASE_URL = "https://api.lusha.com/v3"

PROSPECTING_ENDPOINT = f"{BASE_URL}/contacts/prospecting"
ENRICH_ENDPOINT = f"{BASE_URL}/contacts/enrich"


class LushaProspectingClient:

    def __init__(self, timeout=self.timeout):
        self.api_key = LUSHA_API_KEY

        if not self.api_key:
            raise ValueError("LUSHA_API_KEY is missing from .env")

        if self.api_key.startswith("your_"):
            raise ValueError("Replace the placeholder LUSHA_API_KEY in .env")

        self.timeout = int(timeout)
        self.session = requests.Session()

        self.session.headers.update({
            "api_key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    def _post(self, endpoint, payload):
        response = self.session.post(
            endpoint,
            json=payload,
            timeout=45
        )

        if response.status_code == 401:
            raise RuntimeError("Lusha authentication failed.")

        if response.status_code == 402:
            raise RuntimeError("Lusha returned a credit-related error.")

        if response.status_code == 403:
            # Preserve Lusha's diagnostic message so the dashboard can
            # distinguish inactive account, disabled V3 access, and plan
            # or endpoint permissions. Never include request headers/API key.
            try:
                error_body = response.json()
                detail = error_body.get("message") or error_body.get("error")
                if not detail:
                    detail = str(error_body)
            except ValueError:
                detail = response.text[:1000]

            raise RuntimeError(
                "Lusha returned HTTP 403 (Forbidden): "
                + str(detail)[:1000]
            )

        if response.status_code == 429:
            raise RuntimeError("Lusha rate limit reached.")

        if response.status_code >= 500:
            raise RuntimeError(
                f"Lusha server error: {response.status_code}"
            )

        if not response.ok:
            raise RuntimeError(
                f"Lusha API error {response.status_code}: "
                f"{response.text[:1000]}"
            )

        try:
            return response.json()
        except ValueError:
            raise RuntimeError("Lusha returned invalid JSON.")

    def prospect_contacts(self, payload):
        """
        Search for contacts.
        This method does not reveal contact details.
        """
        if not isinstance(payload, dict) or not payload:
            raise ValueError("A non-empty dictionary payload is required.")

        return self._post(PROSPECTING_ENDPOINT, payload)

    def reveal_contacts(self, contact_ids, reveal):
        """
        Explicitly reveal selected contact fields.

        This method makes a potentially credit-consuming API request.
        It is never called automatically.

        reveal must be 'emails' or 'phones'.
        """

        if not isinstance(contact_ids, list) or not contact_ids:
            raise ValueError("Provide at least one Lusha contact ID.")

        if len(contact_ids) > 100:
            raise ValueError("Maximum 100 contact IDs per request.")

        if reveal not in ("emails", "phones"):
            raise ValueError("Reveal must be 'emails' or 'phones'.")

        clean_ids = list(dict.fromkeys(
            str(contact_id).strip()
            for contact_id in contact_ids
            if contact_id is not None and str(contact_id).strip()
        ))

        if not clean_ids:
            raise ValueError("No valid contact IDs provided.")

        payload = {
            "ids": clean_ids,
            "reveal": [reveal],
            "waterfallEnabled": False
        }

        return self._post(ENRICH_ENDPOINT, payload)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
