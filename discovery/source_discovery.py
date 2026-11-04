
from typing import List, Dict

# Trusted starting points for discovering Indian companies
DISCOVERY_SOURCES = [
    {
        "name": "DTC Connect",
        "url": "https://dtcconnect.in/",
        "type": "D2C Directory"
    },
    {
        "name": "D2C Story",
        "url": "https://www.d2cstory.com/indian-d2c-brands-database/",
        "type": "D2C Database"
    },
    {
        "name": "Inc42",
        "url": "https://inc42.com/",
        "type": "Startup and Funding News"
    },
    {
        "name": "Startup India",
        "url": "https://www.startupindia.gov.in/",
        "type": "Startup Directory"
    },
    {
        "name": "YourStory",
        "url": "https://yourstory.com/",
        "type": "Startup News"
    }
]

# Categories relevant to Quiklee
CATEGORIES = [
    "beauty and personal care",
    "fashion and apparel",
    "food and beverages",
    "health and nutrition",
    "electronics",
    "home and lifestyle",
    "sports and fitness",
    "pet care"
]


def generate_search_queries(category: str) -> List[str]:
    """
    Generate targeted search queries for a company category.
    """

    queries = [
        f"Indian D2C {category} brands official websites",
        f"top {category} startups in India",
        f"fast growing Indian {category} brands",
        f"new {category} brands launched in India",
        f"Indian {category} startups funding 2026",
        f"D2C {category} companies India ecommerce"
    ]

    return queries


def get_all_search_queries() -> List[Dict[str, str]]:
    """
    Generate search queries for all target categories.
    """

    results = []

    for category in CATEGORIES:
        queries = generate_search_queries(category)

        for query in queries:
            results.append({
                "category": category,
                "query": query
            })

    return results


def get_discovery_sources() -> List[Dict[str, str]]:
    return DISCOVERY_SOURCES


if __name__ == "__main__":

    print("\nQUIKLEE COMPANY DISCOVERY ENGINE")
    print("=" * 50)

    print("\nDISCOVERY SOURCES")

    for source in get_discovery_sources():
        print(f"- {source['name']} | {source['type']}")

    queries = get_all_search_queries()

    print(f"\nTotal categories: {len(CATEGORIES)}")
    print(f"Total generated queries: {len(queries)}")

    print("\nSAMPLE SEARCH QUERIES")

    for item in queries[:10]:
        print(f"[{item['category']}] {item['query']}")
