
import requests

API_URL = "https://api.snitch.com/products/plp-details/v2"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://www.snitch.com",
    "Referer": "https://www.snitch.com/"
}

for page in [1, 2, 3]:

    params = {
        "page": page,
        "limit": 30,
        "platform": "web",
        "need_discount_filter": "true",
        "include_plp": "true",
        "include_chips": "false",
        "include_filters": "false"
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()
        plp = data.get("plp") or {}
        plp_data = plp.get("data") or {}
        products = plp_data.get("products") or []

        names = [
            item.get("title")
            for item in products
            if isinstance(item, dict)
        ]

        print(f"\nPAGE {page}")
        print("HTTP STATUS:", response.status_code)
        print("PRODUCT COUNT:", len(products))
        print("FIRST PRODUCT:", names[0] if names else "None")
        print("LAST PRODUCT:", names[-1] if names else "None")

    except Exception as error:
        print(f"\nPAGE {page} ERROR:", error)
