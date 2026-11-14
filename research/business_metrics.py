
from typing import Optional, Dict


def estimate_monthly_orders(
    monthly_visits: Optional[int],
    conversion_rate_min: float = 0.01,
    conversion_rate_max: float = 0.03
) -> Dict:

    if monthly_visits is None:
        return {
            "estimated_monthly_orders_min": None,
            "estimated_monthly_orders_max": None,
            "status": "traffic data unavailable"
        }

    if monthly_visits < 0:
        raise ValueError("Monthly visits cannot be negative.")

    if not (
        0 <= conversion_rate_min <= conversion_rate_max <= 1
    ):
        raise ValueError("Invalid conversion rate range.")

    min_orders = round(monthly_visits * conversion_rate_min)
    max_orders = round(monthly_visits * conversion_rate_max)

    return {
        "estimated_monthly_orders_min": min_orders,
        "estimated_monthly_orders_max": max_orders,
        "conversion_rate_min": conversion_rate_min,
        "conversion_rate_max": conversion_rate_max,
        "estimation_method": "Traffic x assumed conversion rate",
        "data_type": "estimated",
        "status": "estimated"
    }


def estimate_monthly_revenue(
    monthly_orders_min: Optional[int],
    monthly_orders_max: Optional[int],
    aov: Optional[float] = None
) -> Dict:

    if monthly_orders_min is None or monthly_orders_max is None:
        return {
            "estimated_revenue_min": None,
            "estimated_revenue_max": None,
            "status": "order data unavailable"
        }

    if aov is None:
        return {
            "estimated_revenue_min": None,
            "estimated_revenue_max": None,
            "status": "AOV unavailable"
        }

    if aov < 0:
        raise ValueError("AOV cannot be negative.")

    return {
        "estimated_revenue_min": round(monthly_orders_min * aov),
        "estimated_revenue_max": round(monthly_orders_max * aov),
        "aov_used": aov,
        "currency": "INR",
        "status": "estimated"
    }


def estimate_cod_orders(
    monthly_orders_min: Optional[int],
    monthly_orders_max: Optional[int],
    cod_share: Optional[float] = None
) -> Dict:

    if monthly_orders_min is None or monthly_orders_max is None:
        return {
            "estimated_cod_orders_min": None,
            "estimated_cod_orders_max": None,
            "status": "order data unavailable"
        }

    if cod_share is None:
        return {
            "estimated_cod_orders_min": None,
            "estimated_cod_orders_max": None,
            "status": "COD share unavailable"
        }

    if not 0 <= cod_share <= 1:
        raise ValueError("COD share must be between 0 and 1.")

    return {
        "estimated_cod_orders_min": round(monthly_orders_min * cod_share),
        "estimated_cod_orders_max": round(monthly_orders_max * cod_share),
        "cod_share_used": cod_share,
        "status": "estimated"
    }


def calculate_business_metrics(
    monthly_visits: Optional[int],
    aov: Optional[float] = None,
    cod_share: Optional[float] = None,
    conversion_rate_min: float = 0.01,
    conversion_rate_max: float = 0.03
) -> Dict:

    orders = estimate_monthly_orders(
        monthly_visits,
        conversion_rate_min,
        conversion_rate_max
    )

    revenue = estimate_monthly_revenue(
        orders.get("estimated_monthly_orders_min"),
        orders.get("estimated_monthly_orders_max"),
        aov
    )

    cod = estimate_cod_orders(
        orders.get("estimated_monthly_orders_min"),
        orders.get("estimated_monthly_orders_max"),
        cod_share
    )

    return {
        "monthly_visits": monthly_visits,
        **orders,
        **revenue,
        **cod,
        "overall_data_type": (
            "estimated" if monthly_visits is not None else "unavailable"
        ),
        "note": (
            "Orders are estimates based on an assumed conversion rate. "
            "Revenue and COD orders require their respective inputs."
            if monthly_visits is not None
            else "Traffic data is unavailable. No orders, revenue, or COD "
                 "figures have been fabricated."
        )
    }


if __name__ == "__main__":

    print("\nQUIKLEE BUSINESS METRICS ENGINE")
    print("=" * 55)

    result = calculate_business_metrics(
        monthly_visits=None,
        aov=None,
        cod_share=None
    )

    for key, value in result.items():
        print(f"{key}: {value}")
