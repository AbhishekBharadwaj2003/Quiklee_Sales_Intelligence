
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QuikleeResearch/1.0)"
}

TIMEOUT = 20

SOCIAL_DOMAINS = {
    "instagram": "instagram.com",
    "linkedin": "linkedin.com",
    "facebook": "facebook.com",
    "youtube": "youtube.com",
    "twitter": "twitter.com",
    "x": "x.com"
}

IMPORTANT_PAGES = [
    "about",
    "contact",
    "products",
    "shop",
    "collections",
    "pages/about-us",
    "pages/contact-us"
]


def fetch_page(url):
    """Download a publicly accessible HTML page."""

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        if "text/html" not in response.headers.get(
            "Content-Type", ""
        ).lower():
            return None

        return response.text

    except requests.RequestException as error:
        print(f"Unable to fetch {url}: {error}")
        return None


def clean_text(text):
    """Clean extracted website text."""

    return re.sub(r"\s+", " ", text).strip()


def extract_metadata(soup):
    """Extract website title and description."""

    title = (
        clean_text(soup.title.get_text())
        if soup.title else ""
    )

    description_tag = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    description = ""

    if description_tag:
        description = description_tag.get("content", "")

    return {
        "website_title": title,
        "website_description": clean_text(description)
    }


def extract_social_links(soup):
    """Find official social media links."""

    social_links = {}

    for link in soup.find_all("a", href=True):

        href = link["href"].strip()

        for platform, domain in SOCIAL_DOMAINS.items():

            if domain in urlparse(href).netloc.lower():
                social_links[platform] = href

    return social_links


def extract_important_pages(soup, base_url):
    """Identify important internal website pages."""

    pages = {}

    base_domain = urlparse(base_url).netloc.lower()

    for link in soup.find_all("a", href=True):

        href = urljoin(base_url, link["href"])

        parsed = urlparse(href)

        if parsed.netloc.lower() != base_domain:
            continue

        path = parsed.path.lower()

        for page_type in IMPORTANT_PAGES:

            if page_type in path and page_type not in pages:
                pages[page_type] = href

    return pages


def extract_products(soup):
    """Extract product names and visible prices."""

    products = []

    product_containers = soup.select(
        "[class*='product'], "
        "[class*='Product'], "
        "[data-product]"
    )

    seen = set()

    for container in product_containers:

        name_tag = container.select_one(
            "h2, h3, h4, "
            "[class*='title'], "
            "[class*='name']"
        )

        if not name_tag:
            continue

        name = clean_text(name_tag.get_text())

        if not name or name in seen:
            continue

        seen.add(name)

        price_text = ""

        price_tag = container.select_one(
            "[class*='price'], "
            "[class*='Price'], "
            "[data-price]"
        )

        if price_tag:
            price_text = clean_text(
                price_tag.get_text()
            )

        products.append({
            "product_name": name,
            "displayed_price": price_text
        })

        if len(products) >= 30:
            break

    return products


def extract_business_information(soup):
    """Extract visible business information."""

    text = clean_text(
        soup.get_text(" ", strip=True)
    )

    return {
        "page_text_sample": text[:5000],
        "page_text_length": len(text)
    }


def research_company(website_url):
    """Run the complete homepage research process."""

    print(f"\nResearching: {website_url}")

    html = fetch_page(website_url)

    if not html:
        return {
            "website_url": website_url,
            "research_status": "failed"
        }

    soup = BeautifulSoup(html, "lxml")

    metadata = extract_metadata(soup)

    social_links = extract_social_links(soup)

    important_pages = extract_important_pages(
        soup,
        website_url
    )

    products = extract_products(soup)

    business_info = extract_business_information(soup)

    return {
        "website_url": website_url,
        **metadata,
        "social_links": social_links,
        "important_pages": important_pages,
        "products": products,
        **business_info,
        "research_status": "completed"
    }


if __name__ == "__main__":

    test_website = "https://www.mamaearth.in/"

    result = research_company(test_website)

    print("\nQUIKLEE WEBSITE RESEARCH")
    print("=" * 55)

    for key, value in result.items():

        if key == "page_text_sample":
            print(f"\n{key}: {value[:500]}...")

        else:
            print(f"\n{key}: {value}")
