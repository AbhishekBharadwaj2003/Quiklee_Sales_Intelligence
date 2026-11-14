
from statistics import median

from database.company_repository import (
    get_company_by_id,
    update_company
)

from database.research_repository import (
    get_company_research_history
)

from qualification.lead_scoring import calculate_lead_score
from database.campaign_research_queue import get_campaign_research_queue


TRAFFIC_THRESHOLD = 100000


def get_latest_research(research_history, research_type):
    """Return the latest research record of a given type."""

    for record in research_history:
        if record.get("research_type") == research_type:
            return record.get("findings") or {}

    return {}


def extract_product_prices(products):
    """Extract valid positive displayed product prices."""

    prices = []

    for product in products:

        try:
            price = float(product.get("displayed_price"))

            if price > 0:
                prices.append(price)

        except (TypeError, ValueError):
            continue

    return prices


def calculate_catalogue_breadth_score(catalogue_count):
    """
    Calculate an indicative product assortment score.

    This is a catalogue breadth proxy, not shipment volume.
    """

    if catalogue_count is None:
        return None

    if catalogue_count >= 5000:
        return 10
    elif catalogue_count >= 2000:
        return 9
    elif catalogue_count >= 1000:
        return 8
    elif catalogue_count >= 500:
        return 7
    elif catalogue_count >= 100:
        return 6
    elif catalogue_count >= 50:
        return 5

    return 3


def calculate_price_positioning_score(median_price):
    """
    Calculate an indicative product price positioning score.

    This is not an actual average order value score.
    """

    if median_price is None:
        return None

    if median_price >= 4000:
        return 10
    elif median_price >= 2500:
        return 8
    elif median_price >= 1500:
        return 7
    elif median_price >= 1000:
        return 6
    elif median_price >= 500:
        return 4

    return 2


def derive_qualification_inputs(research_history):
    """Derive qualification inputs from available research evidence."""

    website = get_latest_research(
        research_history,
        "website_research"
    )

    traffic = get_latest_research(
        research_history,
        "traffic_analysis"
    )

    metrics = get_latest_research(
        research_history,
        "business_metrics"
    )

    products = website.get("products") or []

    # Product catalogue information
    reported_count = website.get("catalogue_product_count")

    if isinstance(reported_count, (int, float)) and reported_count > 0:
        catalogue_count = int(reported_count)
        catalogue_count_source = "API-reported catalogue count"
    elif products:
        catalogue_count = len(products)
        catalogue_count_source = "Observed extracted product count"
    else:
        catalogue_count = None
        catalogue_count_source = "Unavailable"

    # Product price analysis
    prices = extract_product_prices(products)

    median_price = round(median(prices), 2) if prices else None
    average_price = (
        round(sum(prices) / len(prices), 2)
        if prices else None
    )

    # Shipping potential proxy
    shipping_score = calculate_catalogue_breadth_score(
        catalogue_count
    )

    # AOV / product price positioning proxy
    price_score = calculate_price_positioning_score(
        median_price
    )

    # E-commerce relevance
    if products:
        ecommerce_score = 9
        ecommerce_evidence = (
            "Product catalogue successfully extracted from website."
        )
    elif website.get("important_pages"):
        ecommerce_score = 6
        ecommerce_evidence = (
            "Commercial website pages identified; "
            "product catalogue unavailable."
        )
    else:
        ecommerce_score = None
        ecommerce_evidence = "Insufficient e-commerce evidence."

    # Actual traffic, orders and revenue are kept separate
    monthly_visits = traffic.get("monthly_visits")

    if monthly_visits is None:
        monthly_visits = metrics.get("monthly_visits")

    # COD and growth are not inferred from catalogue data.
    business_inputs = {
        "shipping_potential": shipping_score,
        "aov": price_score,
        "cod_potential": None,
        "growth": None,
        "ecommerce_relevance": ecommerce_score,
        "company_scale": None
    }

    evidence = {
        "shipping_potential": {
            "score": shipping_score,
            "type": "proxy",
            "source": catalogue_count_source,
            "catalogue_count": catalogue_count,
            "explanation": (
                "Product assortment breadth is used as an "
                "indicative shipping potential proxy. "
                "It does not represent shipment volume."
            )
        },
        "aov": {
            "score": price_score,
            "type": "proxy",
            "source": "Displayed product selling prices",
            "products_with_valid_prices": len(prices),
            "median_displayed_price": median_price,
            "average_displayed_price": average_price,
            "explanation": (
                "Product price positioning proxy. "
                "Not actual customer average order value."
            )
        },
        "cod_potential": {
            "score": None,
            "type": "unavailable",
            "explanation": "Verified COD share is unavailable."
        },
        "growth": {
            "score": None,
            "type": "unavailable",
            "explanation": "Verified growth evidence is unavailable."
        },
        "ecommerce_relevance": {
            "score": ecommerce_score,
            "type": "evidence_based",
            "source": "Official website and product catalogue",
            "explanation": ecommerce_evidence
        },
        "company_scale": {
            "score": None,
            "type": "unavailable",
            "explanation": "Verified company scale information is unavailable."
        }
    }

    return {
        "business_inputs": business_inputs,
        "evidence": evidence,
        "catalogue_count": catalogue_count,
        "median_displayed_price": median_price,
        "average_displayed_price": average_price,
        "monthly_visits": monthly_visits,
        "research_status": {
            "website": website.get("research_status", "unavailable"),
            "traffic": traffic.get("traffic_status", "unavailable"),
            "business_metrics": metrics.get(
                "overall_data_type",
                "unavailable"
            )
        }
    }


def qualify_company(company_id: int, business_inputs=None, campaign_id=None):
    """
    Calculate and save an evidence-based qualification score.

    When campaign_id is supplied, campaign traffic eligibility is enforced:
    - 100,000 or more monthly visitors: qualification is allowed.
    - Below 100,000: qualification is blocked.
    - Pending or conflicting traffic: qualification is blocked for review.

    Omitting campaign_id preserves the existing standalone qualification
    workflow for backwards compatibility. Campaign workflows should always
    supply campaign_id so the traffic gate is enforced.
    """

    company = get_company_by_id(company_id)

    if not company:
        raise ValueError(f"Company ID {company_id} not found.")

    campaign_eligibility = None

    if campaign_id is not None:
        campaign_queue = get_campaign_research_queue(campaign_id)
        campaign_entry = next(
            (
                item for item in campaign_queue
                if item["company_id"] == company_id
            ),
            None,
        )

        if campaign_entry is None:
            raise ValueError(
                f"Company ID {company_id} is not linked to campaign "
                f"{campaign_id}."
            )

        campaign_eligibility = {
            "campaign_id": campaign_id,
            "traffic_status": campaign_entry["traffic_status"],
            "monthly_visits": campaign_entry["monthly_visits"],
            "threshold": TRAFFIC_THRESHOLD,
            "research_status": campaign_entry["research_status"],
        }

        if campaign_entry["traffic_status"] != "qualified":
            if campaign_entry["traffic_status"] == "below_threshold":
                raise ValueError(
                    f"Qualification blocked: {company['company_name']} has "
                    f"{campaign_entry['monthly_visits']:,.0f} monthly visitors. "
                    f"The minimum required is {TRAFFIC_THRESHOLD:,}."
                )

            raise ValueError(
                f"Qualification blocked: traffic for {company['company_name']} "
                f"is {campaign_entry['traffic_status']}. Verify traffic before "
                "qualification."
            )

        if campaign_entry["monthly_visits"] is None or (
            float(campaign_entry["monthly_visits"]) < TRAFFIC_THRESHOLD
        ):
            raise ValueError(
                "Qualification blocked: campaign traffic does not meet the "
                f"minimum threshold of {TRAFFIC_THRESHOLD:,} monthly visitors."
            )

    research_history = get_company_research_history(company_id)

    derived = derive_qualification_inputs(research_history)

    inputs = derived["business_inputs"].copy()

    # Explicitly supplied scores override derived scores.
    if business_inputs is not None:

        allowed_factors = {
            "shipping_potential",
            "aov",
            "cod_potential",
            "growth",
            "ecommerce_relevance",
            "company_scale"
        }

        for factor, value in business_inputs.items():

            if factor not in allowed_factors:
                raise ValueError(
                    f"Unknown qualification factor: {factor}"
                )

            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 10
            ):
                raise ValueError(
                    f"{factor} must be a numeric score between 0 and 10."
                )

            inputs[factor] = value

            if value is not None:
                derived["evidence"][factor] = {
                    "score": value,
                    "type": "manually_supplied",
                    "explanation": (
                        "Score explicitly supplied for qualification."
                    )
                }

    result = calculate_lead_score(
        shipping_potential=inputs["shipping_potential"],
        aov=inputs["aov"],
        cod_potential=inputs["cod_potential"],
        growth=inputs["growth"],
        ecommerce_relevance=inputs["ecommerce_relevance"],
        company_scale=inputs["company_scale"]
    )

    if result["lead_score"] is None:
        raise ValueError(
            "Insufficient information to calculate a qualification score."
        )

    proxy_factors = [
        factor
        for factor, details in derived["evidence"].items()
        if details.get("type") == "proxy"
        and details.get("score") is not None
    ]

    provisional = bool(
        proxy_factors or result["missing_factors"]
    )

    saved_category = result["lead_category"]

    if provisional:
        saved_category = f"{saved_category} (Provisional)"

    update_company(
        company_id,
        {
            "qualification_score": result["lead_score"],
            "qualification_category": saved_category,
            "data_completeness": result["data_completeness"]
        }
    )

    return {
        "company_id": company_id,
        "company_name": company["company_name"],
        "campaign_eligibility": campaign_eligibility,
        "research_records": len(research_history),
        "qualification_status": (
            "provisional" if provisional else "complete"
        ),
        "qualification_category": saved_category,
        "provisional_factors": proxy_factors,
        "research_status": derived["research_status"],
        "catalogue_count": derived["catalogue_count"],
        "median_displayed_price": derived["median_displayed_price"],
        "average_displayed_price": derived["average_displayed_price"],
        "monthly_visits": derived["monthly_visits"],
        "evidence": derived["evidence"],
        **result
    }


if __name__ == "__main__":

    print("\nQUIKLEE AUTOMATED COMPANY QUALIFICATION")
    print("=" * 55)

    from database.company_repository import get_all_companies

    companies = get_all_companies()

    if not companies:
        print("No companies available.")
        raise SystemExit

    for company in companies:
        print(
            f"ID: {company['id']} | "
            f"Company: {company['company_name']}"
        )

    try:
        company_id = int(input("\nEnter company ID: "))

        result = qualify_company(company_id)

        print("\nQUALIFICATION RESULT")
        print("=" * 55)

        for key, value in result.items():
            print(f"{key}: {value}")

    except (ValueError, RuntimeError) as error:
        print("\nQualification error:", error)
