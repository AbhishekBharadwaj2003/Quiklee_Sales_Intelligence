
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
import re


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9"
}

TIMEOUT = (10, 20)
MAX_PRODUCT_PAGES = 5
SNITCH_API_LIMIT = 30
MAX_SNITCH_PAGES = 5

SNITCH_API_URL = "https://api.snitch.com/products/plp-details/v2"

SNITCH_API_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://www.snitch.com",
    "Referer": "https://www.snitch.com/"
}

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

    return re.sub(r"\s+", " ", str(text or "")).strip()


def is_snitch_website(website_url):
    """Identify the official Snitch website."""

    hostname = urlparse(website_url).netloc.lower()
    hostname = hostname.split(":")[0]

    return hostname == "snitch.com" or hostname.endswith(".snitch.com")


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
        hostname = urlparse(href).netloc.lower()

        for platform, domain in SOCIAL_DOMAINS.items():

            if domain in hostname:
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
    """Extract product names and visible prices from HTML."""

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

        if not name or name.lower() in seen:
            continue

        seen.add(name.lower())

        price_text = ""

        price_tag = container.select_one(
            "[class*='price'], "
            "[class*='Price'], "
            "[data-price]"
        )

        if price_tag:
            price_text = clean_text(price_tag.get_text())

        products.append({
            "product_name": name,
            "displayed_price": price_text,
            "source": "HTML"
        })

        if len(products) >= 30:
            break

    return products


def extract_product_urls(
    soup,
    base_url,
    max_products=MAX_PRODUCT_PAGES
):
    """Find product page URLs on the same website."""

    product_urls = []
    seen = set()

    base_domain = urlparse(base_url).netloc.lower()

    for link in soup.find_all("a", href=True):

        product_url = urljoin(base_url, link["href"])
        product_url, _ = urldefrag(product_url)

        parsed = urlparse(product_url)

        if parsed.netloc.lower() != base_domain:
            continue

        if not parsed.path.startswith("/products/"):
            continue

        if product_url not in seen:

            seen.add(product_url)
            product_urls.append(product_url)

        if len(product_urls) >= max_products:
            break

    return product_urls


def extract_jsonld_products(soup):
    """Extract Product information from Schema.org JSON-LD."""

    products = []

    def process_data(data):

        if isinstance(data, list):

            for item in data:
                process_data(item)

            return

        if not isinstance(data, dict):
            return

        if "@graph" in data:
            process_data(data["@graph"])

        product_type = data.get("@type", [])

        if isinstance(product_type, str):
            product_type = [product_type]

        if "Product" not in product_type:
            return

        brand_data = data.get("brand", "")

        if isinstance(brand_data, dict):
            brand = brand_data.get("name", "")
        else:
            brand = brand_data

        offers = data.get("offers", [])

        if isinstance(offers, dict):
            offers = [offers]

        valid_offers = [
            offer for offer in offers
            if isinstance(offer, dict)
        ]

        offer = valid_offers[0] if valid_offers else {}

        image = data.get("image", "")

        if isinstance(image, dict):
            image = image.get("url", "")

        elif isinstance(image, list):

            image = image[0] if image else ""

            if isinstance(image, dict):
                image = image.get("url", "")

        products.append({
            "product_name": clean_text(data.get("name", "")),
            "description": clean_text(data.get("description", "")),
            "brand": brand,
            "sku": data.get("sku", ""),
            "displayed_price": str(offer.get("price", "")),
            "currency": offer.get("priceCurrency", ""),
            "availability": offer.get("availability", ""),
            "product_url": data.get("url", ""),
            "image_url": image,
            "source": "JSON-LD"
        })

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            script_content = script.string or script.get_text()

            if not script_content:
                continue

            data = json.loads(script_content)

            process_data(data)

        except (json.JSONDecodeError, TypeError):
            continue

    return products


def research_product_pages(soup, base_url):
    """Visit product pages and extract structured information."""

    product_urls = extract_product_urls(soup, base_url)

    all_products = []

    print(f"Product pages discovered: {len(product_urls)}")

    for product_url in product_urls:

        print("Researching product:", product_url)

        html = fetch_page(product_url)

        if not html:
            continue

        product_soup = BeautifulSoup(html, "lxml")

        extracted = extract_jsonld_products(product_soup)

        for product in extracted:

            if not product.get("product_url"):
                product["product_url"] = product_url

        all_products.extend(extracted)

    return all_products



def extract_snitch_products(website_url):
    """
    Extract up to five pages of publicly available Snitch catalogue products.
    Each page contains up to SNITCH_API_LIMIT products.
    """

    print("\nUsing Snitch public catalogue API...")

    products = []
    catalogue_count = None
    seen_product_ids = set()
    seen_handles = set()
    seen_titles = set()
    pages_fetched = 0
    page_errors = 0

    for page_number in range(1, MAX_SNITCH_PAGES + 1):
        params = {
            "page": page_number,
            "limit": SNITCH_API_LIMIT,
            "platform": "web",
            "need_discount_filter": "true",
            "include_plp": "true",
            "include_chips": "true" if page_number == 1 else "false",
            "include_filters": "false"
        }

        try:
            response = requests.get(
                SNITCH_API_URL,
                params=params,
                headers=SNITCH_API_HEADERS,
                timeout=30
            )

            print(
                f"Snitch API page {page_number} status:",
                response.status_code
            )
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, dict):
                print(f"Unexpected response format on page {page_number}.")
                page_errors += 1
                break

            plp_section = data.get("plp") or {}
            if not isinstance(plp_section, dict):
                plp_section = {}

            plp_data = plp_section.get("data") or {}
            if not isinstance(plp_data, dict):
                plp_data = {}

            raw_products = plp_data.get("products") or []
            if not isinstance(raw_products, list):
                raw_products = []

            if page_number == 1:
                chips_section = data.get("chips") or {}
                if not isinstance(chips_section, dict):
                    chips_section = {}

                chips_summary = chips_section.get("summary") or {}
                if isinstance(chips_summary, dict):
                    catalogue_count = chips_summary.get(
                        "overall_product_count"
                    )

                if catalogue_count is None:
                    catalogue_count = plp_data.get(
                        "overall_product_count"
                    )

                print("Catalogue products reported:", catalogue_count)

            pages_fetched += 1
            print(
                f"Products returned on page {page_number}: "
                f"{len(raw_products)}"
            )

            if not raw_products:
                print(
                    f"No products returned on page {page_number}; "
                    "stopping pagination."
                )
                break

            new_products_on_page = 0

            for item in raw_products:
                if not isinstance(item, dict):
                    continue

                product_id = str(
                    item.get("shopify_product_id") or ""
                ).strip()
                handle = clean_text(item.get("handle", "")).lower()
                title = clean_text(item.get("title", "")).lower()

                # Prefer stable product ID, then handle, then title.
                if product_id and product_id in seen_product_ids:
                    continue
                if not product_id and handle and handle in seen_handles:
                    continue
                if not product_id and not handle and title and title in seen_titles:
                    continue

                if product_id:
                    seen_product_ids.add(product_id)
                if handle:
                    seen_handles.add(handle)
                if title:
                    seen_titles.add(title)

                product_url = (
                    urljoin(
                        "https://www.snitch.com/products/",
                        item.get("handle", "")
                    )
                    if item.get("handle") else ""
                )

                variants = item.get("variants") or []
                if not isinstance(variants, list):
                    variants = []

                sizes = [
                    str(variant.get("size"))
                    for variant in variants
                    if isinstance(variant, dict)
                    and variant.get("size") is not None
                ]

                inventory_values = [
                    variant.get("inventory_quantity")
                    for variant in variants
                    if isinstance(variant, dict)
                    and isinstance(
                        variant.get("inventory_quantity"),
                        (int, float)
                    )
                ]

                total_inventory = (
                    sum(inventory_values)
                    if inventory_values
                    else None
                )

                image_url = (
                    item.get("cdn_preview_image")
                    or item.get("preview_image")
                    or ""
                )

                product = {
                    "product_name": clean_text(item.get("title", "")),
                    "description": clean_text(
                        item.get("short_description", "")
                    ),
                    "brand": "Snitch",
                    "sku": product_id,
                    "displayed_price": str(
                        item.get("selling_price", "")
                    ),
                    "mrp": item.get("mrp"),
                    "currency": "INR",
                    "category": item.get("shopify_product_type", ""),
                    "average_rating": item.get("average_rating"),
                    "total_ratings_count": item.get(
                        "total_ratings_count"
                    ),
                    "total_reviews_count": item.get(
                        "total_rewiews_count"
                    ),
                    "image_url": image_url,
                    "product_url": product_url,
                    "product_handle": item.get("handle", ""),
                    "product_status": item.get("status", ""),
                    "created_at": item.get("created_at", ""),
                    "updated_at": item.get("updated_at", ""),
                    "available_sizes": sizes,
                    "variant_count": len(variants),
                    "inventory_quantity": total_inventory,
                    "source": "Snitch Public Catalogue API"
                }

                if product["product_name"]:
                    products.append(product)
                    new_products_on_page += 1

            print(
                f"New unique products collected from page "
                f"{page_number}: {new_products_on_page}"
            )

        except requests.RequestException as error:
            print(
                f"Snitch API request failed on page "
                f"{page_number}: {error}"
            )
            page_errors += 1
            break

        except (ValueError, TypeError, KeyError) as error:
            print(
                f"Snitch API parsing failed on page "
                f"{page_number}: {error}"
            )
            page_errors += 1
            break

    if page_errors and products:
        api_status = "partial"
    elif products:
        api_status = "success"
    else:
        api_status = "failed"

    print(f"\nSnitch pages fetched: {pages_fetched}")
    print(f"Snitch unique products extracted: {len(products)}")

    return {
        "products": products,
        "catalogue_product_count": catalogue_count,
        "pages_fetched": pages_fetched,
        "api_status": api_status
    }


def merge_products(structured_products, css_products):
    """Combine product sources and remove duplicates."""

    products = []
    seen_products = set()

    for product in structured_products + css_products:

        product_name = clean_text(
            product.get("product_name", "")
        ).lower()

        if not product_name or product_name in seen_products:
            continue

        seen_products.add(product_name)
        products.append(product)

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


def failed_research_result(website_url):
    """Return a consistent structure when website research fails."""

    return {
        "website_url": website_url,
        "website_title": "",
        "website_description": "",
        "social_links": {},
        "important_pages": {},
        "products": [],
        "catalogue_product_count": None,
        "catalogue_pages_fetched": None,
        "catalogue_api_status": None,
        "page_text_sample": "",
        "page_text_length": 0,
        "useful_data_points": 0,
        "migration_detected": False,
        "research_quality": "unavailable",
        "research_status": "failed"
    }


def research_company(website_url):
    """Run the complete homepage and product research process."""

    print(f"\nResearching: {website_url}")

    html = fetch_page(website_url)

    if not html:
        return failed_research_result(website_url)

    soup = BeautifulSoup(html, "lxml")

    # STEP 1: Website metadata
    metadata = extract_metadata(soup)

    # STEP 2: Social links
    social_links = extract_social_links(soup)

    # STEP 3: Important internal pages
    important_pages = extract_important_pages(
        soup,
        website_url
    )

    catalogue_product_count = None
    catalogue_pages_fetched = None
    catalogue_api_status = None

    # STEP 4: Brand-specific Snitch catalogue research
    if is_snitch_website(website_url):

        snitch_result = extract_snitch_products(website_url)

        products = snitch_result["products"]

        catalogue_product_count = snitch_result[
            "catalogue_product_count"
        ]
        catalogue_pages_fetched = snitch_result["pages_fetched"]
        catalogue_api_status = snitch_result["api_status"]

        # Fall back to the regular extraction methods if API fails.
        if not products:

            print(
                "\nSnitch API did not return products. "
                "Trying regular website extraction..."
            )

            css_products = extract_products(soup)

            structured_products = research_product_pages(
                soup,
                website_url
            )

            products = merge_products(
                structured_products,
                css_products
            )

    else:

        # STEP 5: Products from visible HTML
        print("\nExtracting visible HTML products...")

        css_products = extract_products(soup)

        # STEP 6: Products from individual product pages
        print("\nExtracting structured JSON-LD products...")

        structured_products = research_product_pages(
            soup,
            website_url
        )

        # STEP 7: Combine and deduplicate products
        products = merge_products(
            structured_products,
            css_products
        )

    print(f"\nTotal unique products extracted: {len(products)}")

    # STEP 8: Business information
    business_info = extract_business_information(soup)

    # STEP 9: Check for website migration notices
    page_content = (
        metadata.get("website_title", "") + " " +
        metadata.get("website_description", "") + " " +
        business_info.get("page_text_sample", "")
    ).lower()

    migration_signals = [
        "we are now",
        "moved to our new website",
        "visit our new website",
        "upgraded new experience",
        "redirecting you to our new website"
    ]

    migration_detected = any(
        signal in page_content
        for signal in migration_signals
    )

    # STEP 10: Assess website and catalogue research separately.
    # A successful product API response must not hide weak website-level
    # information or missing business details.
    website_data_points = sum([
        bool(metadata.get("website_title")),
        bool(metadata.get("website_description")),
        bool(social_links),
        bool(important_pages),
        business_info.get("page_text_length", 0) > 500
    ])

    catalogue_data_points = sum([
        bool(products),
        (
            catalogue_api_status in ("success", "partial")
            if catalogue_api_status is not None
            else False
        )
    ])

    useful_data_points = website_data_points + catalogue_data_points

    # STEP 11: Assign research quality.
    if migration_detected:
        research_status = "partial"
        research_quality = "website_migration_detected"

    elif is_snitch_website(website_url):
        if (
            catalogue_api_status == "success"
            and len(products) >= 100
            and website_data_points >= 3
        ):
            research_status = "completed"
            research_quality = "good"

        elif products and catalogue_api_status in ("success", "partial"):
            research_status = "partial"
            research_quality = "catalogue_researched_website_limited"

        elif website_data_points >= 3:
            research_status = "partial"
            research_quality = "website_researched_catalogue_unavailable"

        else:
            research_status = "partial"
            research_quality = "insufficient_information"

    elif website_data_points >= 4 and products:
        research_status = "completed"
        research_quality = "good"

    elif website_data_points >= 2 or products:
        research_status = "partial"
        research_quality = "limited"

    else:
        research_status = "partial"
        research_quality = "insufficient_information"

    # STEP 12: Return research results
    return {
        "website_url": website_url,
        **metadata,
        "social_links": social_links,
        "important_pages": important_pages,
        "products": products,
        "catalogue_product_count": catalogue_product_count,
        "catalogue_pages_fetched": catalogue_pages_fetched,
        "catalogue_api_status": catalogue_api_status,
        **business_info,
        "useful_data_points": useful_data_points,
        "website_data_points": website_data_points,
        "catalogue_data_points": catalogue_data_points,
        "migration_detected": migration_detected,
        "research_quality": research_quality,
        "research_status": research_status
    }


if __name__ == "__main__":

    test_website = "https://www.snitch.com"

    result = research_company(test_website)

    print("\nQUIKLEE WEBSITE RESEARCH")
    print("=" * 55)

    for key, value in result.items():

        if key == "page_text_sample":
            print(f"\n{key}: {value[:500]}...")

        elif key == "products":
            print(f"\n{key}: {len(value)} products")

            for product in value[:5]:
                print(json.dumps(product, indent=2))

        else:
            print(f"\n{key}: {value}")
