
import os
import requests

from dotenv import load_dotenv

load_dotenv()

SIMILARWEB_API_KEY = os.getenv("SIMILARWEB_API_KEY")

BASE_URL = "https://api.similarweb.com/v1/website"


class SimilarwebClient:

    def __init__(self):

        self.api_key = SIMILARWEB_API_KEY

        if not self.api_key:
            raise ValueError(
                "Similarweb API key is missing."
            )

    def get_traffic(
        self,
        domain,
        start_date,
        end_date,
        country="in"
    ):
        """
        Fetch website visit data.

        Requires the appropriate Similarweb API subscription.
        """

        endpoint = (
            f"{BASE_URL}/{domain}/"
            "total-traffic-and-engagement/visits"
        )

        params = {
            "api_key": self.api_key,
            "start_date": start_date,
            "end_date": end_date,
            "country": country,
            "granularity": "monthly"
        }

        try:

            response = requests.get(
                endpoint,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as error:

            status = error.response.status_code

            if status == 401:
                message = "Invalid or unauthorized API key."
            elif status == 403:
                message = "Your subscription may not include this endpoint."
            elif status == 404:
                message = "Traffic data or domain not found."
            elif status == 429:
                message = "API rate limit reached."
            else:
                message = f"Similarweb API error: {status}"

            raise RuntimeError(message) from error

        except requests.exceptions.RequestException as error:

            raise RuntimeError(
                f"Similarweb connection failed: {error}"
            ) from error

    def get_engagement(
        self,
        domain,
        start_date,
        end_date,
        country="in"
    ):
        """
        Fetch website engagement metrics.
        """

        endpoint = (
            f"{BASE_URL}/{domain}/"
            "total-traffic-and-engagement/engagement"
        )

        params = {
            "api_key": self.api_key,
            "start_date": start_date,
            "end_date": end_date,
            "country": country,
            "granularity": "monthly"
        }

        try:

            response = requests.get(
                endpoint,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as error:

            raise RuntimeError(
                f"Similarweb engagement API error: "
                f"{error.response.status_code}"
            ) from error

        except requests.exceptions.RequestException as error:

            raise RuntimeError(
                f"Similarweb connection failed: {error}"
            ) from error


def analyse_traffic(domain, start_date, end_date):

    client = SimilarwebClient()

    traffic = client.get_traffic(
        domain,
        start_date,
        end_date
    )

    engagement = client.get_engagement(
        domain,
        start_date,
        end_date
    )

    return {
        "domain": domain,
        "traffic_data": traffic,
        "engagement_data": engagement,
        "data_source": "Similarweb",
        "research_status": "completed"
    }


if __name__ == "__main__":

    print("\nQUIKLEE TRAFFIC ANALYSIS")
    print("=" * 50)

    try:

        result = analyse_traffic(
            domain="mamaearth.in",
            start_date="2026-08",
            end_date="2026-10"
        )

        print("\nDomain:", result["domain"])
        print("\nTraffic Data:")
        print(result["traffic_data"])

        print("\nEngagement Data:")
        print(result["engagement_data"])

    except (ValueError, RuntimeError) as error:

        print("\nTraffic analysis unavailable:", error)
