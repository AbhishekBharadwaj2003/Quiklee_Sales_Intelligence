
import argparse
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import pandas as pd
import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "verified_websites.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "website_contacts.csv"

REQUEST_TIMEOUT = 15
MAX_CONTACT_PAGES = 7
REQUEST_DELAY = 0.3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

ALLOWED_PATH_PATTERNS = [
    r"contact", r"contact-us", r"contactus",
    r"about", r"about-us", r"reach-us",
    r"customer-care", r"customer-support",
    r"support", r"help", r"store-locator",
    r"storelocator", r"find-a-store", r"our-stores",
]

STORE_PATH_KEYWORDS = [
    "store-locator",
    "storelocator",
    "find-a-store",
    "our-stores",
    "store-list",
]

IGNORED_PATH_KEYWORDS = [
    "/products", "/product", "/collections", "/collection",
    "/category", "/categories", "/blog", "/blogs",
    "/news", "/campaign", "/campaigns", "/cart",
    "/checkout", "/search", "/account", "/policies",
    "/pages/faq", "/faq", "/track", "/tracking",
    "/wishlist", "/offers", "/sale",
]

INVALID_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net",
    "test.com", "test.org", "domain.com",
    "email.com", "yourcompany.com", "company.com",
    "sentry.io", "wixpress.com",
}

INVALID_EMAIL_PREFIXES = {
    "test", "testing", "example", "demo",
    "noreply", "no-reply", "donotreply", "do-not-reply",
}

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?91[\s.-]?)?(?:0[\s.-]?)?"
    r"[6-9]\d{4}[\s.-]?\d{5}(?!\d)"
)


def clean_value(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_domain(url):
    try:
        parsed = urlparse(
            url if url.startswith(("http://", "https://"))
            else f"https://{url}"
        )
        return (parsed.hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("91") and len(digits) == 12:
        return "+" + digits
    if len(digits) == 10:
        return "+91" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+91" + digits[1:]

    return ""


def is_valid_email(email):
    email = email.lower().strip()

    if not EMAIL_PATTERN.fullmatch(email):
        return False

    local_part, domain = email.rsplit("@", 1)

    if domain in INVALID_EMAIL_DOMAINS:
        return False
    if local_part in INVALID_EMAIL_PREFIXES:
        return False
    if ".." in email:
        return False

    return True


def categorize_email(email):
    local_part = email.split("@")[0].lower()

    if any(x in local_part for x in [
        "career", "hr", "jobs", "recruitment"
    ]):
        return "careers"

    if any(x in local_part for x in [
        "collab", "influencer", "partnership", "creator"
    ]):
        return "collaboration"

    if any(x in local_part for x in [
        "support", "care", "help", "grievance"
    ]):
        return "support"

    if any(x in local_part for x in [
        "sales", "business", "enquiry", "inquiry"
    ]):
        return "business"

    return "general"


def extract_emails(text):
    found = set()

    for email in EMAIL_PATTERN.findall(text):
        email = email.lower().strip(".,;:")
        if is_valid_email(email):
            found.add(email)

    return sorted(found)


def extract_phones(text):
    found = set()

    for match in PHONE_PATTERN.findall(text):
        phone = normalize_phone(match)
        if phone:
            found.add(phone)

    return sorted(found)


def get_page_content(url, session):
    try:
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "text/html" not in content_type:
            return None, None

        return response.url, BeautifulSoup(
            response.text, "html.parser"
        )

    except requests.exceptions.RequestException as error:
        print(f"  Unable to access {url}: {error}")
        return None, None


def is_ignored_path(path):
    path = path.lower()
    return any(keyword in path for keyword in IGNORED_PATH_KEYWORDS)


def is_store_page(url):
    path = urlparse(url).path.lower()
    return any(keyword in path for keyword in STORE_PATH_KEYWORDS)


def is_relevant_contact_path(path):
    path = path.lower().rstrip("/")

    if is_ignored_path(path):
        return False

    segments = [x for x in path.split("/") if x]

    if not segments:
        return False

    last_segment = segments[-1]

    return any(
        re.search(pattern, last_segment)
        for pattern in ALLOWED_PATH_PATTERNS
    )


def find_contact_pages(base_url, soup):
    base_domain = normalize_domain(base_url)
    discovered = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()

        if not href:
            continue

        absolute_url = urljoin(base_url, href)
        absolute_url, _ = urldefrag(absolute_url)
        parsed = urlparse(absolute_url)

        if parsed.scheme not in ("http", "https"):
            continue

        if normalize_domain(absolute_url) != base_domain:
            continue

        if not is_relevant_contact_path(parsed.path):
            continue

        clean_url = parsed._replace(
            query="", fragment=""
        ).geturl()

        if clean_url.rstrip("/") != base_url.rstrip("/"):
            discovered.add(clean_url)

    def priority(url):
        path = urlparse(url).path.lower()

        if "contact" in path:
            return 0
        if "support" in path or "customer-care" in path:
            return 1
        if is_store_page(url):
            return 2
        if "about" in path:
            return 3
        if "help" in path:
            return 4

        return 5

    return sorted(
        discovered,
        key=lambda url: (priority(url), url)
    )[:MAX_CONTACT_PAGES]


def extract_page_contacts(soup):
    for element in soup([
        "script", "style", "noscript", "svg"
    ]):
        element.decompose()

    page_text = soup.get_text(" ", strip=True)

    emails = set(extract_emails(page_text))
    phones = set(extract_phones(page_text))

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip().lower()
            if is_valid_email(email):
                emails.add(email)

        elif href.lower().startswith("tel:"):
            phone = normalize_phone(href[4:])
            if phone:
                phones.add(phone)

    return sorted(emails), sorted(phones)


def get_content_hash(soup):
    for element in soup([
        "script", "style", "noscript", "svg"
    ]):
        element.decompose()

    text = soup.get_text(" ", strip=True).lower()
    normalized = re.sub(r"\s+", " ", text).strip()

    return normalized


def empty_result(status):
    return {
        "pages_checked": 0,
        "duplicate_pages_skipped": 0,
        "business_emails": [],
        "support_emails": [],
        "careers_emails": [],
        "collaboration_emails": [],
        "general_emails": [],
        "business_phones": [],
        "store_phones": [],
        "email_sources": [],
        "phone_sources": [],
        "extraction_status": status,
    }


def format_source_records(source_map):
    return [
        f"{contact} | {'; '.join(sorted(urls))}"
        for contact, urls in sorted(source_map.items())
    ]


def extract_company_contacts(company_name, website_url):
    if not website_url:
        return empty_result("missing_website")

    session = requests.Session()
    session.headers.update(HEADERS)

    homepage_url, homepage_soup = get_page_content(
        website_url, session
    )

    if homepage_soup is None:
        session.close()
        return empty_result("website_unreachable")

    contact_pages = find_contact_pages(
        homepage_url, homepage_soup
    )

    pages_to_visit = [homepage_url] + contact_pages

    email_sources = {}
    business_phone_sources = {}
    store_phone_sources = {}

    visited_urls = set()
    content_hashes = set()

    pages_checked = 0
    duplicate_pages_skipped = 0

    try:
        for page_url in pages_to_visit:
            if page_url.rstrip("/") in visited_urls:
                continue

            visited_urls.add(page_url.rstrip("/"))

            if page_url == homepage_url:
                final_url = homepage_url
                page_soup = homepage_soup
            else:
                final_url, page_soup = get_page_content(
                    page_url, session
                )

            if page_soup is None:
                continue

            # Work on a copy so the original soup remains intact.
            hash_soup = BeautifulSoup(
                str(page_soup), "html.parser"
            )
            content_hash = get_content_hash(hash_soup)

            if content_hash in content_hashes:
                duplicate_pages_skipped += 1
                print(
                    f"  Skipped duplicate content: {final_url}"
                )
                continue

            content_hashes.add(content_hash)
            pages_checked += 1

            emails, phones = extract_page_contacts(
                page_soup
            )

            for email in emails:
                email_sources.setdefault(
                    email, set()
                ).add(final_url)

            target_phone_sources = (
                store_phone_sources
                if is_store_page(final_url)
                else business_phone_sources
            )

            for phone in phones:
                target_phone_sources.setdefault(
                    phone, set()
                ).add(final_url)

            print(
                f"  Checked: {final_url} | "
                f"Emails: {len(emails)} | "
                f"Phones: {len(phones)}"
            )

            time.sleep(REQUEST_DELAY)

    finally:
        session.close()

    # If a phone appears on both a store page and a central page,
    # retain it as a business number and remove it from store-only.
    for phone in list(store_phone_sources):
        if phone in business_phone_sources:
            del store_phone_sources[phone]

    categorized = {
        "business": [],
        "support": [],
        "careers": [],
        "collaboration": [],
        "general": [],
    }

    for email in email_sources:
        categorized[categorize_email(email)].append(email)

    all_phones = (
        set(business_phone_sources)
        | set(store_phone_sources)
    )

    status = (
        "contacts_found"
        if email_sources or all_phones
        else "no_public_contacts_found"
    )

    return {
        "pages_checked": pages_checked,
        "duplicate_pages_skipped": duplicate_pages_skipped,
        "business_emails": sorted(categorized["business"]),
        "support_emails": sorted(categorized["support"]),
        "careers_emails": sorted(categorized["careers"]),
        "collaboration_emails": sorted(
            categorized["collaboration"]
        ),
        "general_emails": sorted(categorized["general"]),
        "business_phones": sorted(business_phone_sources),
        "store_phones": sorted(store_phone_sources),
        "email_sources": format_source_records(email_sources),
        "phone_sources": (
            [
                "BUSINESS: " + item
                for item in format_source_records(
                    business_phone_sources
                )
            ]
            +
            [
                "STORE: " + item
                for item in format_source_records(
                    store_phone_sources
                )
            ]
        ),
        "extraction_status": status,
    }


def load_previous_results(output_file):
    output_file = Path(output_file)

    if not output_file.exists():
        return {}

    dataframe = pd.read_csv(output_file).fillna("")
    results = {}

    for _, row in dataframe.iterrows():
        company = clean_value(
            row.get("company_name")
        ).lower()

        if company:
            results[company] = row.to_dict()

    return results


def save_results(records, output_file):
    output_file = Path(output_file)
    output_file.parent.mkdir(
        parents=True, exist_ok=True
    )

    pd.DataFrame(records).to_csv(
        output_file, index=False
    )


def run_extraction(
    input_file=DEFAULT_INPUT,
    output_file=DEFAULT_OUTPUT,
    limit=None,
    resume=True,
):
    input_file = Path(input_file)

    if not input_file.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_file}"
        )

    dataframe = pd.read_csv(input_file)

    required_columns = [
        "company_name",
        "candidate_website",
        "verification_status",
    ]

    missing = [
        col for col in required_columns
        if col not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    eligible_statuses = {
        "likely_company_match",
        "needs_review",
    }

    dataframe = dataframe[
        dataframe["verification_status"].isin(
            eligible_statuses
        )
    ].copy()

    if limit is not None:
        dataframe = dataframe.head(limit)

    previous_results = (
        load_previous_results(output_file)
        if resume else {}
    )

    processed_results = dict(previous_results)

    print("\nQUIKLEE WEBSITE CONTACT EXTRACTION")
    print("=" * 55)

    total = len(dataframe)

    for index, (_, row) in enumerate(
        dataframe.iterrows(), start=1
    ):
        company_name = clean_value(
            row.get("company_name")
        )
        company_key = company_name.lower()

        if not company_name:
            continue

        if company_key in processed_results:
            print(
                f"\n[{index}/{total}] "
                f"Skipping {company_name}: already processed."
            )
            continue

        website = (
            clean_value(row.get("final_url"))
            or clean_value(row.get("candidate_website"))
        )

        print(
            f"\n[{index}/{total}] Processing: {company_name}"
        )

        result = extract_company_contacts(
            company_name, website
        )

        record = {
            "company_name": company_name,
            "website": website,
            "verification_status": clean_value(
                row.get("verification_status")
            ),
            "pages_checked": result["pages_checked"],
            "duplicate_pages_skipped": result[
                "duplicate_pages_skipped"
            ],
            "business_emails": "; ".join(
                result["business_emails"]
            ),
            "support_emails": "; ".join(
                result["support_emails"]
            ),
            "careers_emails": "; ".join(
                result["careers_emails"]
            ),
            "collaboration_emails": "; ".join(
                result["collaboration_emails"]
            ),
            "general_emails": "; ".join(
                result["general_emails"]
            ),
            "business_phones": "; ".join(
                result["business_phones"]
            ),
            "store_phones": "; ".join(
                result["store_phones"]
            ),
            "email_sources": " || ".join(
                result["email_sources"]
            ),
            "phone_sources": " || ".join(
                result["phone_sources"]
            ),
            "extraction_status": result[
                "extraction_status"
            ],
        }

        processed_results[company_key] = record

        save_results(
            list(processed_results.values()),
            output_file
        )

        for category in [
            "business_emails",
            "support_emails",
            "careers_emails",
            "collaboration_emails",
            "general_emails",
            "business_phones",
            "store_phones",
        ]:
            print(
                f"{category}: {len(result[category])}"
            )

        print(
            "Duplicate pages skipped:",
            result["duplicate_pages_skipped"]
        )

    final_dataframe = pd.DataFrame(
        processed_results.values()
    )

    print("\n" + "=" * 55)
    print("CONTACT EXTRACTION SUMMARY")
    print("=" * 55)

    print("Companies in output:", len(final_dataframe))

    if not final_dataframe.empty:
        print(
            "Companies with contacts:",
            (
                final_dataframe["extraction_status"]
                == "contacts_found"
            ).sum()
        )

        print(
            "Companies without public contacts:",
            (
                final_dataframe["extraction_status"]
                == "no_public_contacts_found"
            ).sum()
        )

    print("\nOutput saved to:")
    print(output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract public company emails and phones."
    )

    parser.add_argument(
        "--input", default=str(DEFAULT_INPUT)
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT)
    )
    parser.add_argument(
        "--limit", type=int, default=None
    )
    parser.add_argument(
        "--no-resume", action="store_true"
    )

    args = parser.parse_args()

    run_extraction(
        input_file=args.input,
        output_file=args.output,
        limit=args.limit,
        resume=not args.no_resume,
    )
