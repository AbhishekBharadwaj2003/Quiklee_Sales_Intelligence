
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

USER_AGENT = (
    "Mozilla/5.0 (compatible; QuikleeResearchBot/1.0; "
    "+https://example.com/bot)"
)

TIMEOUT = 15

ECOMMERCE_SIGNALS = [
    "add to cart",
    "buy now",
    "shop now",
    "shopping cart",
    "checkout",
    "products",
    "collections",
    "free shipping",
    "delivery",
    "orders"
]

INDIA_SIGNALS = [
    "india",
    "indian",
    "inr",
    "₹",
    "+91",
    "gstin",
    "made in india"
]


def fetch_website(url: str):
    """Fetch a company's homepage."""

    headers = {
        "User-Agent": USER_AGENT
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        if "text/html" not in content_type.lower():
            return None, "Website did not return HTML content"

        return response.text, None

    except requests.exceptions.Timeout:
        return None, "Website request timed out"

    except requests.exceptions.RequestException as error:
        return None, str(error)


def extract_website_information(html: str, url: str) -> dict:
    """Extract basic business information from homepage HTML."""

    soup = BeautifulSoup(html, "html.parser")

    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title else ""
    )

    meta_description = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    description = (
        meta_description.get("content", "").strip()
        if meta_description else ""
    )

    page_text = soup.get_text(" ", strip=True).lower()

    links = [
        link.get("href", "")
        for link in soup.find_all("a", href=True)
    ]

    domain = urlparse(url).netloc.lower()

    ecommerce_matches = [
        signal for signal in ECOMMERCE_SIGNALS
        if signal in page_text
    ]

    india_matches = [
        signal for signal in INDIA_SIGNALS
        if signal in page_text
    ]

    return {
        "official_website": url,
        "domain": domain,
        "website_title": title,
        "website_description": description,
        "ecommerce_signals": ecommerce_matches,
        "india_signals": india_matches,
        "total_links": len(links)
    }


def validate_company(candidate: dict) -> dict:
    """Validate a discovered company candidate."""

    url = candidate.get("website_url", "")

    html, error = fetch_website(url)

    if error:
        return {
            **candidate,
            "validation_status": "unreachable",
            "validation_reason": error
        }

    information = extract_website_information(html, url)

    has_business_identity = bool(
        information["website_title"]
        or information["website_description"]
    )

    has_ecommerce_signals = bool(
        information["ecommerce_signals"]
    )

    has_india_signals = bool(
        information["india_signals"]
        or urlparse(url).hostname.endswith(".in")
    )

    if not has_business_identity:
        status = "needs_review"
        reason = "Insufficient business identity information"

    elif has_ecommerce_signals and has_india_signals:
        status = "promising_candidate"
        reason = "Website has e-commerce and India-related signals"

    elif has_ecommerce_signals:
        status = "needs_review"
        reason = "E-commerce signals found; Indian business relevance needs verification"

    else:
        status = "needs_review"
        reason = "Business relevance needs manual verification"

    return {
        **candidate,
        **information,
        "validation_status": status,
        "validation_reason": reason
    }


if __name__ == "__main__":

    test_candidate = {
        "company_name_candidate": "Example Indian Store",
        "website_url": "https://www.example.com/",
        "category": "Fashion and Apparel",
        "discovery_source": "Manual Test"
    }

    print("\nQUIKLEE COMPANY VALIDATION")
    print("=" * 50)

    result = validate_company(test_candidate)

    print("Company:", result["company_name_candidate"])
    print("Website:", result["website_url"])
    print("Status:", result["validation_status"])
    print("Reason:", result["validation_reason"])
