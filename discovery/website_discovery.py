
import argparse
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from discovery.brave_search import BraveSearchClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = PROJECT_ROOT / "data" / "Quiklee Sales CRM - Leads.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "website_discovery_results.csv"

BLOCKED_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "protonmail.com",
    "rediffmail.com",
    "aol.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "pinterest.com",
    "crunchbase.com",
    "justdial.com",
    "indiamart.com",
    "tradeindia.com",
    "zaubacorp.com",
    "tofler.in"
}


def clean_value(value):
    """Convert missing values to clean strings."""

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_domain(url):
    """Extract a normalized domain from a URL."""

    if not url:
        return ""

    try:
        parsed = urlparse(
            url if url.startswith(("http://", "https://"))
            else f"https://{url}"
        )

        domain = parsed.netloc.lower().split("@")[-1]
        domain = domain.split(":")[0]

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def is_blocked_domain(domain):
    """Identify generic email providers and non-company platforms."""

    return any(
        domain == blocked or domain.endswith("." + blocked)
        for blocked in BLOCKED_DOMAINS
    )


def extract_email_domains(email_value):
    """Extract unique company domains from one or more email addresses."""

    if not email_value:
        return []

    emails = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        email_value
    )

    domains = []

    for email in emails:

        domain = email.rsplit("@", 1)[-1].lower()

        if domain and not is_blocked_domain(domain):
            if domain not in domains:
                domains.append(domain)

    return domains


def company_name_tokens(company_name):
    """Generate useful company name tokens."""

    ignored = {
        "private", "limited", "ltd", "pvt",
        "llp", "india", "the", "and",
        "company", "co"
    }

    tokens = re.findall(
        r"[a-z0-9]+",
        company_name.lower()
    )

    return [
        token for token in tokens
        if token not in ignored and len(token) > 1
    ]


def calculate_match_score(company_name, title, url):
    """Estimate how closely a search result matches a company."""

    domain = normalize_domain(url)

    if not domain or is_blocked_domain(domain):
        return 0

    tokens = company_name_tokens(company_name)

    if not tokens:
        return 0

    title_tokens = set(
        re.findall(r"[a-z0-9]+", title.lower())
    )

    domain_tokens = set(
        re.findall(r"[a-z0-9]+", domain)
    )

    score = 0

    for token in tokens:

        if token in title_tokens:
            score += 3

        if token in domain_tokens:
            score += 2

    if all(token in title_tokens for token in tokens):
        score += 2

    return score


def load_dataset(file_path):
    """Load the original CRM CSV."""

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"CRM dataset not found: {file_path}"
        )

    dataframe = pd.read_csv(file_path)

    if "Brand Name" not in dataframe.columns:
        raise ValueError(
            "Brand Name column is missing."
        )

    for column in ["Website", "Email "]:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe


def load_previous_results(output_file):
    """Load existing checkpoint results."""

    output_file = Path(output_file)

    if not output_file.exists():
        return {}

    previous = pd.read_csv(output_file).fillna("")

    results = {}

    for _, row in previous.iterrows():

        company_name = clean_value(
            row.get("company_name")
        ).lower()

        if company_name:
            results[company_name] = row.to_dict()

    return results


def get_email_domain_candidate(email_value):
    """Use an existing company email to identify a possible domain."""

    domains = extract_email_domains(email_value)

    if not domains:
        return None

    if len(domains) > 1:
        return {
            "website": "",
            "domain": "",
            "source": "CRM email",
            "match_score": 0,
            "status": "multiple_email_domains_review"
        }

    domain = domains[0]

    return {
        "website": f"https://{domain}",
        "domain": domain,
        "source": "CRM email domain",
        "match_score": 0,
        "status": "email_domain_candidate"
    }


def discover_company_website(
    client,
    company_name,
    email_value=""
):
    """Discover a website using CRM data first and Brave second."""

    email_candidate = get_email_domain_candidate(
        email_value
    )

    if email_candidate:
        return email_candidate

    if client is None:
        return {
            "website": "",
            "domain": "",
            "source": "Not available",
            "match_score": 0,
            "status": "awaiting_brave_api"
        }

    query = f'"{company_name}" India official website'

    results = client.search(
        query=query,
        count=10,
        country="IN"
    )

    candidates = []

    for result in results:

        url = clean_value(result.get("url"))
        title = clean_value(result.get("title"))
        description = clean_value(
            result.get("description")
        )

        domain = normalize_domain(url)

        if not domain or is_blocked_domain(domain):
            continue

        score = calculate_match_score(
            company_name,
            title,
            url
        )

        if score <= 0:
            continue

        candidates.append({
            "website": f"https://{domain}",
            "domain": domain,
            "title": title,
            "description": description,
            "match_score": score,
            "source": "Brave Search"
        })

    if not candidates:
        return {
            "website": "",
            "domain": "",
            "source": "Brave Search",
            "match_score": 0,
            "status": "manual_review"
        }

    candidates.sort(
        key=lambda item: item["match_score"],
        reverse=True
    )

    best = candidates[0]

    # Require a stronger match before accepting a search result.
    if best["match_score"] >= 5:
        status = "candidate_found"
    else:
        status = "manual_review"

    return {
        **best,
        "status": status
    }


def save_checkpoint(records, output_file):
    """Save all processed records after each company."""

    output_file = Path(output_file)
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    dataframe = pd.DataFrame(records)

    dataframe.to_csv(
        output_file,
        index=False
    )


def run_website_discovery(
    input_file=DEFAULT_INPUT,
    output_file=DEFAULT_OUTPUT,
    limit=None,
    delay=1.0,
    resume=True
):
    """Run resumable website discovery."""

    dataframe = load_dataset(input_file)

    if limit:
        dataframe = dataframe.head(limit).copy()

    if dataframe.empty:
        print("No companies found.")
        return

    previous_results = (
        load_previous_results(output_file)
        if resume else {}
    )

    client = None

    try:
        possible_client = BraveSearchClient()

        api_key = clean_value(
            possible_client.api_key
        )

        if (
            api_key
            and api_key != "your_brave_api_key"
            and not api_key.lower().startswith("your_")
        ):
            client = possible_client
            print("Brave API configured.")
        else:
            print("Brave API placeholder detected.")
            print("Continuing with offline email-domain discovery.")

    except ValueError:
        print("Brave API key unavailable.")
        print("Continuing with offline email-domain discovery.")

    processed_results = dict(previous_results)

    processed_names = set()

    print("\nQUIKLEE WEBSITE DISCOVERY")
    print("=" * 50)

    total = len(dataframe)

    for index, (_, row) in enumerate(
        dataframe.iterrows(),
        start=1
    ):

        company_name = clean_value(
            row.get("Brand Name")
        )

        company_key = company_name.lower()

        if not company_name:
            continue

        # Process duplicate company names only once.
        if company_key in processed_names:
            continue

        processed_names.add(company_key)

        existing_result = processed_results.get(
            company_key
        )

        if existing_result:

            status = clean_value(
                existing_result.get("discovery_status")
            )

            if status in {
                "existing_website",
                "email_domain_candidate",
                "candidate_found"
            }:
                print(
                    f"\n[{index}/{total}] "
                    f"Skipping {company_name}: already processed."
                )
                continue

        existing_website = clean_value(
            row.get("Website")
        )

        email_value = clean_value(
            row.get("Email ")
        )

        print(
            f"\n[{index}/{total}] "
            f"Processing: {company_name}"
        )

        if existing_website:

            domain = normalize_domain(existing_website)

            result = {
                "website": existing_website,
                "domain": domain,
                "source": "Existing CRM data",
                "match_score": 100,
                "status": "existing_website"
            }

        else:

            try:
                result = discover_company_website(
                    client,
                    company_name,
                    email_value
                )

            except RuntimeError as error:

                print("Search error:", error)

                error_text = str(error).lower()

                if (
                    "rate limit" in error_text
                    or "429" in error_text
                    or "unauthorized" in error_text
                    or "401" in error_text
                ):
                    print(
                        "Stopping to prevent further API requests."
                    )
                    break

                result = {
                    "website": "",
                    "domain": "",
                    "source": "Brave Search",
                    "match_score": 0,
                    "status": "search_failed"
                }

        print(
            "Website:",
            result.get("website") or "Not found"
        )

        print(
            "Status:",
            result["status"]
        )

        processed_results[company_key] = {
            "company_name": company_name,
            "website": result.get("website", ""),
            "domain": result.get("domain", ""),
            "match_score": result.get("match_score", 0),
            "source": result.get("source", ""),
            "discovery_status": result["status"]
        }

        # Save after every processed company.
        save_checkpoint(
            list(processed_results.values()),
            output_file
        )

        if client is not None:
            time.sleep(max(0, delay))

    final_records = list(
        processed_results.values()
    )

    output_dataframe = pd.DataFrame(
        final_records
    )

    print("\n" + "=" * 50)
    print("WEBSITE DISCOVERY SUMMARY")
    print("=" * 50)

    print("Unique companies in this run:", len(processed_names))
    print("Saved discovery records:", len(output_dataframe))

    if not output_dataframe.empty:

        print(
            "Existing websites:",
            (
                output_dataframe["discovery_status"]
                == "existing_website"
            ).sum()
        )

        print(
            "Email domain candidates:",
            (
                output_dataframe["discovery_status"]
                == "email_domain_candidate"
            ).sum()
        )

        print(
            "Brave candidates:",
            (
                output_dataframe["discovery_status"]
                == "candidate_found"
            ).sum()
        )

        print(
            "Manual review:",
            output_dataframe["discovery_status"].isin([
                "manual_review",
                "multiple_email_domains_review"
            ]).sum()
        )

    print("\nCheckpoint saved at:")
    print(output_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Quiklee website discovery"
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
        default=1.0
    )

    parser.add_argument(
        "--no-resume",
        action="store_true"
    )

    args = parser.parse_args()

    run_website_discovery(
        input_file=args.input,
        output_file=args.output,
        limit=args.limit,
        delay=args.delay,
        resume=not args.no_resume
    )
