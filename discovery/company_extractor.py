
from urllib.parse import urlparse
from typing import List, Dict
import tldextract


# Initialize extractor without requiring an internet connection
domain_extractor = tldextract.TLDExtract(
    suffix_list_urls=()
)

EXCLUDED_DOMAINS = {
    "google.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
    "amazon.in",
    "flipkart.com"
}


def extract_domain(url: str) -> str:
    """Extract registered domain from URL."""

    try:
        extracted = domain_extractor(url)

        if not extracted.domain or not extracted.suffix:
            return ""

        return f"{extracted.domain}.{extracted.suffix}".lower()

    except Exception as error:
        print(f"Domain extraction error: {error}")
        return ""


def is_valid_candidate_url(url: str) -> bool:

    if not url:
        return False

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        domain = extract_domain(url)

        if not domain or domain in EXCLUDED_DOMAINS:
            return False

        return True

    except Exception:
        return False


def extract_company_candidates(
    search_results: List[Dict],
    category: str,
    query: str,
    source: str = "Brave Search"
) -> List[Dict]:

    candidates = []
    seen_domains = set()

    for result in search_results:

        title = result.get("title", "").strip()
        url = result.get("url", "").strip()
        description = result.get("description", "").strip()

        if not title or not is_valid_candidate_url(url):
            continue

        domain = extract_domain(url)

        if domain in seen_domains:
            continue

        seen_domains.add(domain)

        candidates.append({
            "company_name_candidate": title,
            "website_url": url,
            "domain": domain,
            "description": description,
            "category": category,
            "discovery_query": query,
            "discovery_source": source,
            "verification_status": "pending"
        })

    return candidates


if __name__ == "__main__":

    sample_results = [
        {
            "title": "Example Beauty Brand",
            "url": "https://www.examplebeauty.in/",
            "description": "An Indian D2C skincare brand."
        },
        {
            "title": "Example Fashion Store",
            "url": "https://www.examplefashion.com/",
            "description": "Online fashion and apparel brand."
        },
        {
            "title": "Example Beauty Brand",
            "url": "https://examplebeauty.in/about",
            "description": "About the company."
        },
        {
            "title": "Instagram Page",
            "url": "https://www.instagram.com/example/",
            "description": "Social media profile."
        }
    ]

    extracted = extract_company_candidates(
        search_results=sample_results,
        category="Beauty and Personal Care",
        query="Indian D2C beauty brands"
    )

    print("\nCOMPANY EXTRACTION TEST")
    print("=" * 50)

    print(f"Candidates extracted: {len(extracted)}")

    for company in extracted:
        print("\nCompany:", company["company_name_candidate"])
        print("Website:", company["website_url"])
        print("Domain:", company["domain"])
        print("Status:", company["verification_status"])
