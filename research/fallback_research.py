
from typing import Dict, List
from urllib.parse import urlparse

from discovery.brave_search import BraveSearchClient
from database.research_repository import add_research_record


def generate_fallback_queries(
    company_name: str,
    website_url: str = ""
) -> List[str]:
    """Generate product and business research queries."""

    domain = urlparse(website_url).netloc.lower()
    domain = domain.removeprefix("www.")

    queries = [
        f'"{company_name}" official products catalogue India',
        f'"{company_name}" products prices India',
        f'"{company_name}" product categories official website',
        f'"{company_name}" latest products launches India',
        f'"{company_name}" company business information India'
    ]

    if domain:
        queries.insert(0, f"site:{domain} products catalogue")

    return queries


def collect_fallback_research(
    company_name: str,
    website_url: str = "",
    company_id: int = None,
    results_per_query: int = 5
) -> Dict:
    """
    Collect publicly indexed company and product information.

    Saves both successful and failed research attempts.
    Search results remain unverified until independently checked.
    """

    queries = generate_fallback_queries(
        company_name,
        website_url
    )

    all_results = []
    seen_urls = set()
    research_error = None
    completed_queries = 0

    print("\nQUIKLEE FALLBACK RESEARCH")
    print("=" * 55)
    print("Company:", company_name)

    try:
        client = BraveSearchClient()

        for index, query in enumerate(queries, start=1):

            print(f"\n[{index}/{len(queries)}] Searching: {query}")

            results = client.search(
                query=query,
                count=results_per_query
            )

            completed_queries += 1

            for result in results:

                url = result.get("url", "").strip()

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

                all_results.append({
                    "company_name": company_name,
                    "research_query": query,
                    "title": result.get("title", ""),
                    "url": url,
                    "description": result.get("description", ""),
                    "source": result.get("source", ""),
                    "verification_status": "unverified"
                })

    except Exception as error:

        research_error = (
            f"{type(error).__name__}: {error}"
        )

        print("\nFallback research error:", research_error)

    # Determine research status.
    if research_error and all_results:
        research_status = "partial"

    elif research_error:
        research_status = "failed"

    elif all_results:
        research_status = "completed"

    else:
        research_status = "insufficient"

    # Prepare complete research record.
    research_result = {
        "company_name": company_name,
        "website_url": website_url,
        "research_method": "public_search_fallback",
        "total_queries": len(queries),
        "completed_queries": completed_queries,
        "total_results_found": len(all_results),
        "research_results": all_results,
        "verification_status": "unverified",
        "research_status": research_status,
        "error": research_error
    }

    # Save successful, partial and failed attempts.
    if company_id is not None:

        try:
            add_research_record(
                company_id=company_id,
                research_type="fallback_research",
                source="Brave Search",
                source_url=website_url or None,
                findings=research_result,
                confidence="unverified"
            )

            print("\nFallback research attempt saved to database.")

        except Exception as save_error:

            print(
                "\nUnable to save fallback research:",
                save_error
            )

            raise

    print("\nFALLBACK RESEARCH SUMMARY")
    print("-" * 45)
    print("Queries:", len(queries))
    print("Completed queries:", completed_queries)
    print("Results found:", len(all_results))
    print("Status:", research_status)

    if research_error:
        print("Error:", research_error)

    return research_result


if __name__ == "__main__":

    try:

        result = collect_fallback_research(
            company_name="Wakefit",
            website_url="https://www.wakefit.co",
            company_id=5
        )

        print("\nFinal status:", result["research_status"])

    except Exception as error:

        print("\nFallback research could not be saved:", error)
