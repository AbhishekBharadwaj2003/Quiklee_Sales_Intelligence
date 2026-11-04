
from typing import Dict, List
from discovery.brave_search import BraveSearchClient


def generate_research_queries(company_name: str) -> List[str]:
    """Generate targeted research queries for a company."""

    return [
        f'"{company_name}" funding investment investors India',
        f'"{company_name}" latest funding round',
        f'"{company_name}" business expansion India',
        f'"{company_name}" latest achievements milestones',
        f'"{company_name}" new product launch partnership',
        f'"{company_name}" revenue growth business news'
    ]


def collect_research(company_name: str) -> Dict:
    """Search for funding and growth-related information."""

    client = BraveSearchClient()

    queries = generate_research_queries(company_name)

    all_results = []
    seen_urls = set()

    for query in queries:

        print(f"Researching: {query}")

        results = client.search(
            query=query,
            count=5
        )

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
                "source": result.get("source", "")
            })

    return {
        "company_name": company_name,
        "total_articles_found": len(all_results),
        "research_results": all_results,
        "research_status": "completed"
    }


def classify_research_results(results: List[Dict]) -> Dict:
    """
    Group search results using keyword signals.
    This is preliminary classification, not factual verification.
    """

    categories = {
        "funding": [
            "funding", "investment", "investor",
            "raised", "series a", "series b",
            "seed round", "venture capital"
        ],
        "expansion": [
            "expansion", "new market", "international",
            "new city", "offline stores", "global"
        ],
        "achievements": [
            "milestone", "achievement", "award",
            "growth", "revenue", "profit"
        ],
        "product_launch": [
            "launch", "new product", "product range",
            "partnership", "collaboration", "acquisition"
        ]
    }

    classified = {
        category: [] for category in categories
    }

    for result in results:

        searchable_text = (
            result.get("title", "") + " " +
            result.get("description", "")
        ).lower()

        for category, keywords in categories.items():

            if any(
                keyword in searchable_text
                for keyword in keywords
            ):
                classified[category].append(result)

    return classified


if __name__ == "__main__":

    company_name = "Mamaearth"

    print("\nQUIKLEE FUNDING & GROWTH RESEARCH")
    print("=" * 55)

    try:

        research = collect_research(company_name)

        classified = classify_research_results(
            research["research_results"]
        )

        print("\nTotal articles found:",
              research["total_articles_found"])

        for category, articles in classified.items():

            print(f"\n{category.upper()}: {len(articles)}")

            for article in articles[:3]:
                print("-", article["title"])
                print("  Source:", article["url"])

    except (ValueError, RuntimeError) as error:

        print("\nResearch could not run:", error)
