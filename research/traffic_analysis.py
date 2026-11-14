
import requests

from config.settings import TABAPI_API_KEY


BASE_URL = "https://tabapi.com/api/v1/domains"


class TabAPIClient:
    """Client for TabAPI website traffic data."""

    def __init__(self):
        self.api_key = TABAPI_API_KEY

        if not self.api_key:
            raise ValueError("TabAPI API key is missing. Check your .env file.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        })

    def get_traffic(self, domain, months=3):
        """Fetch monthly traffic and engagement data for a domain."""

        if not 3 <= months <= 12:
            raise ValueError("Months must be between 3 and 12.")

        domain = domain.strip().lower()

        if domain.startswith(("https://", "http://")):
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc

        if domain.startswith("www."):
            domain = domain[4:]

        endpoint = f"{BASE_URL}/{domain}/traffic"

        try:
            response = self.session.get(
                endpoint,
                params={"months": months},
                timeout=45
            )

            if response.status_code != 200:
                try:
                    error_data = response.json().get("error", {})
                    error_code = error_data.get("code", "unknown")
                    error_message = error_data.get("message", "Unknown API error")
                except ValueError:
                    error_code = "unknown"
                    error_message = response.text[:300]

                messages = {
                    "unauthorized": "TabAPI authentication failed. Check the API key.",
                    "invalid_api_key": "The TabAPI key is invalid or revoked.",
                    "insufficient_credits": "Your TabAPI account has insufficient credits.",
                    "invalid_domain": "The supplied domain is invalid.",
                    "unprocessable": "TabAPI does not have enough traffic history for this domain.",
                    "upstream_error": "The upstream traffic data provider failed.",
                    "upstream_timeout": "The traffic data provider timed out."
                }

                message = messages.get(error_code, error_message)

                raise RuntimeError(
                    f"TabAPI error ({response.status_code}): {message}"
                    f" | Code: {error_code}"
                )

            data = response.json()

            credits_used = response.headers.get("Credits-Charged")

            if credits_used is not None:
                data["_credits_charged"] = credits_used

            return data

        except requests.exceptions.Timeout as error:
            raise RuntimeError("TabAPI request timed out.") from error

        except requests.exceptions.ConnectionError as error:
            raise RuntimeError("Could not connect to TabAPI.") from error

        except requests.exceptions.RequestException as error:
            raise RuntimeError(f"TabAPI request failed: {error}") from error


def extract_monthly_visits(traffic_data):
    """Extract monthly visit history."""

    if not isinstance(traffic_data, dict):
        return []

    return traffic_data.get("monthly_visits", [])


def analyse_traffic(domain, start_date=None, end_date=None, months=3):
    """
    Fetch and structure website traffic intelligence.

    start_date and end_date are retained for compatibility with
    the previous Similarweb function signature.
    TabAPI uses the months parameter instead.
    """

    try:
        client = TabAPIClient()
        data = client.get_traffic(domain, months=months)

        overview = data.get("overview") or {}

        result = {
            "domain": data.get("domain", domain),
            "title": data.get("title"),
            "description": data.get("description"),

            "monthly_visits": overview.get("visits"),
            "reporting_month": overview.get("month"),

            "global_rank": overview.get("global_rank"),
            "country_rank": overview.get("country_rank"),

            "bounce_rate": overview.get("bounce_rate"),
            "pages_per_visit": overview.get("pages_per_visit"),
            "time_on_site_seconds": overview.get("time_on_site_seconds"),

            "monthly_history": extract_monthly_visits(data),
            "traffic_sources": data.get("traffic_sources", {}),
            "top_keywords": data.get("top_keywords", []),
            "top_regions": data.get("top_regions", []),
            "ai_traffic": data.get("ai_traffic"),

            "credits_charged": data.get("_credits_charged"),
            "status": "completed",
            "error": None
        }

        return result

    except (ValueError, RuntimeError) as error:
        return {
            "domain": domain,
            "status": "unavailable",
            "error": str(error)
        }


if __name__ == "__main__":

    domain = "vilvahstore.com"

    print("=" * 55)
    print("QUIKLEE SALES INTELLIGENCE")
    print("TABAPI WEBSITE TRAFFIC TEST")
    print("=" * 55)

    result = analyse_traffic(domain, months=3)

    if result["status"] == "completed":

        print("\nDomain:", result["domain"])
        print("Website:", result["title"])
        print("Reporting month:", result["reporting_month"])

        print("\nTRAFFIC")
        print("Monthly visits:", result["monthly_visits"])
        print("Global rank:", result["global_rank"])
        print("Country rank:", result["country_rank"])

        print("\nENGAGEMENT")
        print("Bounce rate:", result["bounce_rate"])
        print("Pages per visit:", result["pages_per_visit"])
        print("Average session duration (seconds):",
              result["time_on_site_seconds"])

        print("\nMONTHLY VISITS")
        for item in result["monthly_history"]:
            print(item.get("month"), ":", item.get("visits"))

        print("\nTRAFFIC SOURCES")
        for source, share in result["traffic_sources"].items():
            print(f"{source}: {share}")

        print("\nTOP REGIONS")
        for region in result["top_regions"]:
            print(region)

        print("\nTOP KEYWORDS")
        for keyword in result["top_keywords"]:
            print(keyword)

        print("\nCredits charged:", result["credits_charged"])
        print("\nTabAPI integration successful.")

    else:
        print("\nTraffic lookup failed.")
        print("Reason:", result["error"])
