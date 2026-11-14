
import requests
from typing import Dict, List, Optional

from config.settings import BRAVE_API_KEY


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchClient:

    def __init__(self):
        self.api_key = BRAVE_API_KEY

        if not self.api_key:
            raise ValueError(
                "Brave API key missing. Add BRAVE_API_KEY to your .env file."
            )

        self.headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key
        }

    def search(
        self,
        query: str,
        count: int = 10,
        country: str = "IN"
    ) -> List[Dict]:

        params = {
            "q": query,
            "count": count,
            "country": country,
            "search_lang": "en"
        }

        try:
            response = requests.get(
                BRAVE_SEARCH_URL,
                headers=self.headers,
                params=params,
                timeout=20
            )

            if not response.ok:
                print("Brave API Status:", response.status_code)
                print("Brave API Error:", response.text)
                response.raise_for_status()

            data = response.json()

            results = data.get("web", {}).get("results", [])

            companies = []

            for result in results:
                companies.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "description": result.get("description", ""),
                    "source": result.get("profile", {}).get("long_name", "")
                })

            return companies

        except requests.exceptions.HTTPError as error:
            status = error.response.status_code

            if status == 401:
                message = "Invalid or unauthorized Brave API key."
            elif status == 429:
                message = "Brave API rate limit reached."
            else:
                message = f"Brave API HTTP error: {status}"

            raise RuntimeError(message) from error

        except requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"Unable to connect to Brave Search: {error}"
            ) from error

    def search_companies(
        self,
        category: str,
        count: int = 10
    ) -> List[Dict]:

        query = (
            f"Indian D2C {category} brands official website"
        )

        return self.search(query=query, count=count)


if __name__ == "__main__":

    print("\nQUIKLEE BRAVE SEARCH MODULE")
    print("=" * 45)

    try:
        client = BraveSearchClient()

        results = client.search(
            query="Indian D2C skincare brands official websites",
            count=10
        )

        print(f"\nFound {len(results)} results:\n")

        for index, result in enumerate(results, start=1):
            print(f"{index}. {result['title']}")
            print(f"   Website: {result['url']}")
            print(f"   Description: {result['description'][:200]}")
            print()

    except (ValueError, RuntimeError) as error:
        print(f"\nERROR: {error}")
