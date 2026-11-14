
import requests
import json

API_URL = "https://api.snitch.com/products/plp-details/v2"

params = {
    "page": 1,
    "limit": 5,
    "platform": "web",
    "need_discount_filter": "true",
    "include_plp": "true",
    "include_chips": "false",
    "include_filters": "false"
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://www.snitch.com",
    "Referer": "https://www.snitch.com/"
}


def inspect_products(data, path="root"):
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}"

            if isinstance(value, list) and value:
                if isinstance(value[0], dict):
                    print(f"\nPRODUCT-LIKE LIST FOUND: {current_path}")
                    print("RECORD COUNT:", len(value))
                    print("FIRST RECORD:")
                    print(json.dumps(value[0], indent=2)[:5000])

            inspect_products(value, current_path)

    elif isinstance(data, list):
        for index, item in enumerate(data[:3]):
            inspect_products(item, f"{path}[{index}]")


print("Inspecting Snitch product records...\n")

try:
    response = requests.get(
        API_URL,
        params=params,
        headers=headers,
        timeout=30
    )

    print("STATUS:", response.status_code)

    response.raise_for_status()
    data = response.json()

    print("\nTOP-LEVEL KEYS:", list(data.keys()))

    inspect_products(data)

except requests.RequestException as error:
    print("REQUEST ERROR:", error)

except ValueError as error:
    print("JSON ERROR:", error)
