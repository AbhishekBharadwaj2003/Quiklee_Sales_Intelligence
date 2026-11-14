
import os
import requests

from dotenv import load_dotenv

load_dotenv()


LUSHA_BASE_URL = "https://api.lusha.com/v3"

CONTACT_SEARCH_ENDPOINT = (
    f"{LUSHA_BASE_URL}/contacts/search"
)


class LushaClient:

    def __init__(self):

        self.api_key = os.getenv("LUSHA_API_KEY")

        if not self.api_key:
            raise ValueError(
                "LUSHA_API_KEY is missing. "
                "Add the company-provided key to your .env file."
            )

        if self.api_key.startswith("your_"):
            raise ValueError(
                "LUSHA_API_KEY is still a placeholder."
            )

        self.headers = {
            "api_key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def search_contacts(self, contacts):
        """
        Search Lusha for existing contact profiles.

        This is a search/preview operation.
        It does not request email or phone reveal fields.
        """

        if not isinstance(contacts, list) or not contacts:
            raise ValueError(
                "Provide at least one contact to search."
            )

        if len(contacts) > 100:
            raise ValueError(
                "Maximum 100 contacts allowed per request."
            )

        validated_contacts = []

        for index, contact in enumerate(contacts, start=1):

            if not isinstance(contact, dict):
                raise ValueError(
                    f"Contact {index} must be a dictionary."
                )

            first_name = contact.get("firstName", "").strip()
            last_name = contact.get("lastName", "").strip()
            company_name = contact.get("companyName", "").strip()
            company_domain = contact.get("companyDomain", "").strip()
            email = contact.get("email", "").strip()
            linkedin_url = contact.get("linkedinUrl", "").strip()

            has_name_and_company = (
                first_name
                and last_name
                and (company_name or company_domain)
            )

            has_identifier = (
                has_name_and_company
                or email
                or linkedin_url
                or contact.get("id")
            )

            if not has_identifier:
                raise ValueError(
                    f"Contact {index} needs an email, LinkedIn URL, "
                    "contact ID, or first name + last name + company."
                )

            payload_contact = {
                "clientReferenceId": str(
                    contact.get(
                        "clientReferenceId",
                        f"quiklee-contact-{index}"
                    )
                )
            }

            if first_name:
                payload_contact["firstName"] = first_name

            if last_name:
                payload_contact["lastName"] = last_name

            if company_name:
                payload_contact["companyName"] = company_name

            if company_domain:
                payload_contact["companyDomain"] = company_domain

            if email:
                payload_contact["email"] = email

            if linkedin_url:
                payload_contact["linkedinUrl"] = linkedin_url

            if contact.get("id"):
                payload_contact["id"] = str(contact["id"])

            validated_contacts.append(payload_contact)

        payload = {
            "contacts": validated_contacts,
            "options": {
                "includePartialProfiles": True
            }
        }

        try:
            response = self.session.post(
                CONTACT_SEARCH_ENDPOINT,
                json=payload,
                timeout=30
            )

            if response.status_code == 401:
                raise RuntimeError(
                    "Lusha authentication failed. "
                    "Check whether the API key is valid."
                )

            if response.status_code == 402:
                raise RuntimeError(
                    "Lusha returned Payment Required. "
                    "Check available API credits and plan access."
                )

            if response.status_code == 403:
                raise RuntimeError(
                    "Lusha access forbidden. "
                    "Your account may not have V3 API access enabled."
                )

            if response.status_code == 429:
                raise RuntimeError(
                    "Lusha rate limit reached. "
                    "Wait before trying again."
                )

            if response.status_code >= 500:
                raise RuntimeError(
                    f"Lusha server error: HTTP {response.status_code}"
                )

            if not response.ok:
                try:
                    error_data = response.json()
                except ValueError:
                    error_data = response.text

                raise RuntimeError(
                    f"Lusha API error ({response.status_code}): "
                    f"{error_data}"
                )

            return response.json()

        except requests.exceptions.Timeout as error:
            raise RuntimeError(
                "Lusha API request timed out."
            ) from error

        except requests.exceptions.ConnectionError as error:
            raise RuntimeError(
                "Unable to connect to Lusha API."
            ) from error

        except requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"Lusha request failed: {error}"
            ) from error

    def close(self):
        self.session.close()


if __name__ == "__main__":

    try:
        client = LushaClient()

        print("Lusha API key detected.")
        print("Lusha V3 client initialized.")
        print("Contact search endpoint configured.")
        print("No API request has been made.")

        client.close()

    except (ValueError, RuntimeError) as error:
        print("Lusha configuration error:")
        print(error)
