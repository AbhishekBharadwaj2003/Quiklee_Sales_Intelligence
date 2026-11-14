
import argparse
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "website_discovery_results.csv"
)

DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "verified_websites.csv"
)

REQUEST_TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

PARKED_KEYWORDS = [
    "domain for sale",
    "buy this domain",
    "domain parking",
    "this domain is parked",
    "coming soon",
    "website coming soon",
    "under construction",
    "default web page",
    "website not configured"
]


def clean_value(value):
    """Convert missing values into clean strings."""

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_domain(url):
    """Extract the hostname from a URL."""

    if not url:
        return ""

    try:
        parsed = urlparse(
            url if url.startswith(("http://", "https://"))
            else f"https://{url}"
        )

        domain = parsed.hostname or ""

        return domain.lower().removeprefix("www.")

    except Exception:
        return ""


def normalize_text(value):
    """Normalize text for company-name matching."""

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_value(value).lower()
    ).strip()


def calculate_relevance(company_name, page_title, description):
    """Estimate whether the website content matches the company."""

    company_tokens = set(
        normalize_text(company_name).split()
    )

    ignored_tokens = {
        "private", "limited", "ltd", "pvt",
        "llp", "india", "the", "and", "company"
    }

    company_tokens -= ignored_tokens

    if not company_tokens:
        return 0

    website_text = normalize_text(
        f"{page_title} {description}"
    )

    website_tokens = set(website_text.split())

    matched = company_tokens.intersection(website_tokens)

    return round(
        len(matched) / len(company_tokens) * 100,
        2
    )


def is_parked_website(page_title, description, page_text):
    """Detect common domain parking and placeholder messages."""

    content = normalize_text(
        f"{page_title} {description} {page_text[:5000]}"
    )

    return any(
        keyword in content
        for keyword in PARKED_KEYWORDS
    )


def verify_website(company_name, website_url):
    """Check website availability and inspect its homepage."""

    if not website_url:
        return {
            "final_url": "",
            "domain": "",
            "http_status": "",
            "page_title": "",
            "description": "",
            "relevance_score": 0,
            "verification_status": "missing_website",
            "verification_message": "No website candidate available."
        }

    domain = normalize_domain(website_url)

    if not domain:
        return {
            "final_url": "",
            "domain": "",
            "http_status": "",
            "page_title": "",
            "description": "",
            "relevance_score": 0,
            "verification_status": "invalid_url",
            "verification_message": "Invalid website URL."
        }

    # Try HTTPS first, then HTTP if necessary.
    urls_to_try = [
        f"https://{domain}",
        f"http://{domain}"
    ]

    last_error = ""

    for url in urls_to_try:

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            status_code = response.status_code

            if status_code >= 400:
                last_error = f"HTTP {status_code}"
                continue

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "text/html" not in content_type:
                return {
                    "final_url": response.url,
                    "domain": normalize_domain(response.url),
                    "http_status": status_code,
                    "page_title": "",
                    "description": "",
                    "relevance_score": 0,
                    "verification_status": "needs_review",
                    "verification_message": (
                        "Website responded, but did not return HTML."
                    )
                }

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            title_tag = soup.find("title")

            page_title = (
                title_tag.get_text(" ", strip=True)
                if title_tag else ""
            )

            description_tag = soup.find(
                "meta",
                attrs={"name": re.compile("^description$", re.I)}
            )

            description = (
                description_tag.get("content", "").strip()
                if description_tag else ""
            )

            page_text = soup.get_text(
                " ",
                strip=True
            )

            relevance = calculate_relevance(
                company_name,
                page_title,
                description
            )

            if is_parked_website(
                page_title,
                description,
                page_text
            ):
                verification_status = "parked_suspected"
                message = "Website appears to be parked or a placeholder."

            elif relevance >= 50:
                verification_status = "likely_company_match"
                message = (
                    "Website is reachable and its page metadata "
                    "matches the company name."
                )

            else:
                verification_status = "needs_review"
                message = (
                    "Website is reachable, but company identity "
                    "could not be established confidently."
                )

            return {
                "final_url": response.url,
                "domain": normalize_domain(response.url),
                "http_status": status_code,
                "page_title": page_title,
                "description": description,
                "relevance_score": relevance,
                "verification_status": verification_status,
                "verification_message": message
            }

        except requests.exceptions.SSLError as error:
            last_error = f"SSL error: {error}"

        except requests.exceptions.Timeout:
            last_error = "Website request timed out."

        except requests.exceptions.ConnectionError:
            last_error = "Unable to connect to website."

        except requests.exceptions.RequestException as error:
            last_error = str(error)

        except Exception as error:
            last_error = str(error)

    return {
        "final_url": "",
        "domain": domain,
        "http_status": "",
        "page_title": "",
        "description": "",
        "relevance_score": 0,
        "verification_status": "unreachable",
        "verification_message": last_error
    }


def load_discovery_results(input_file):
    """Load website discovery results."""

    input_file = Path(input_file)

    if not input_file.exists():
        raise FileNotFoundError(
            f"Discovery results not found: {input_file}"
        )

    dataframe = pd.read_csv(input_file)

    required_columns = [
        "company_name",
        "website",
        "domain",
        "source",
        "discovery_status"
    ]

    missing = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    return dataframe


def load_previous_results(output_file):
    """Load previous verification results for resuming."""

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


def save_checkpoint(records, output_file):
    """Save verification results incrementally."""

    output_file = Path(output_file)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    pd.DataFrame(records).to_csv(
        output_file,
        index=False
    )


def run_verification(
    input_file=DEFAULT_INPUT,
    output_file=DEFAULT_OUTPUT,
    limit=None,
    delay=0.5,
    resume=True
):
    """Verify all discovered website candidates."""

    dataframe = load_discovery_results(input_file)

    if limit:
        dataframe = dataframe.head(limit).copy()

    if dataframe.empty:
        print("No website discovery records found.")
        return

    previous_results = (
        load_previous_results(output_file)
        if resume else {}
    )

    processed_results = dict(previous_results)

    print("\nQUIKLEE WEBSITE VERIFICATION")
    print("=" * 55)

    total = len(dataframe)

    for index, (_, row) in enumerate(
        dataframe.iterrows(),
        start=1
    ):

        company_name = clean_value(
            row.get("company_name")
        )

        company_key = company_name.lower()

        if not company_name:
            continue

        previous = processed_results.get(company_key)

        if previous:
            print(
                f"\n[{index}/{total}] "
                f"Skipping {company_name}: already verified."
            )
            continue

        website = clean_value(
            row.get("website")
        )

        print(
            f"\n[{index}/{total}] "
            f"Verifying: {company_name}"
        )

        if not website:

            result = {
                "final_url": "",
                "domain": "",
                "http_status": "",
                "page_title": "",
                "description": "",
                "relevance_score": 0,
                "verification_status": "missing_website",
                "verification_message": (
                    "Website discovery is still pending."
                )
            }

        else:

            result = verify_website(
                company_name,
                website
            )

        print(
            "Website:",
            result["final_url"] or website or "Missing"
        )

        print(
            "Status:",
            result["verification_status"]
        )

        record = {
            "company_name": company_name,
            "candidate_website": website,
            "discovered_domain": clean_value(
                row.get("domain")
            ),
            "discovery_source": clean_value(
                row.get("source")
            ),
            "discovery_status": clean_value(
                row.get("discovery_status")
            ),
            **result
        }

        processed_results[company_key] = record

        save_checkpoint(
            list(processed_results.values()),
            output_file
        )

        time.sleep(max(0, delay))

    final_dataframe = pd.DataFrame(
        processed_results.values()
    )

    print("\n" + "=" * 55)
    print("VERIFICATION SUMMARY")
    print("=" * 55)

    print("Records saved:", len(final_dataframe))

    if not final_dataframe.empty:

        for status, count in (
            final_dataframe["verification_status"]
            .value_counts()
            .items()
        ):
            print(f"{status}: {count}")

    print("\nOutput saved to:")
    print(output_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Verify discovered company websites."
    )

    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT)
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT)
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.5
    )

    parser.add_argument(
        "--no-resume",
        action="store_true"
    )

    args = parser.parse_args()

    run_verification(
        input_file=args.input,
        output_file=args.output,
        limit=args.limit,
        delay=args.delay,
        resume=not args.no_resume
    )
