
from typing import Dict, Optional


WEIGHTS = {
    "shipping_potential": 25,
    "aov": 20,
    "cod_potential": 20,
    "growth": 15,
    "ecommerce_relevance": 10,
    "company_scale": 10
}


def normalize_score(value: Optional[float]) -> float:
    """Convert a score to a valid 0-10 range."""

    if value is None:
        return 0

    return max(0, min(float(value), 10))


def calculate_lead_score(
    shipping_potential: Optional[float],
    aov: Optional[float],
    cod_potential: Optional[float],
    growth: Optional[float],
    ecommerce_relevance: Optional[float],
    company_scale: Optional[float]
) -> Dict:
    """
    Calculate a weighted company qualification score.

    Each input must be a score between 0 and 10.
    Missing information is not treated as a zero:
    the score is calculated only using available factors.
    """

    inputs = {
        "shipping_potential": shipping_potential,
        "aov": aov,
        "cod_potential": cod_potential,
        "growth": growth,
        "ecommerce_relevance": ecommerce_relevance,
        "company_scale": company_scale
    }

    available_scores = {}
    missing_factors = []

    for factor, value in inputs.items():

        if value is None:
            missing_factors.append(factor)
            continue

        available_scores[factor] = normalize_score(value)

    if not available_scores:
        return {
            "lead_score": None,
            "lead_category": "Insufficient data",
            "data_completeness": 0,
            "missing_factors": missing_factors
        }

    available_weight = sum(
        WEIGHTS[factor]
        for factor in available_scores
    )

    weighted_total = sum(
        available_scores[factor] * WEIGHTS[factor]
        for factor in available_scores
    )

    final_score = weighted_total / available_weight

    completeness = available_weight

    if final_score >= 8:
        category = "High Potential"

    elif final_score >= 6:
        category = "Medium Potential"

    elif final_score >= 4:
        category = "Low Potential"

    else:
        category = "Very Low Potential"

    return {
        "lead_score": round(final_score * 10, 2),
        "lead_category": category,
        "data_completeness": completeness,
        "missing_factors": missing_factors,
        "factor_scores": available_scores,
        "scoring_weights": WEIGHTS,
        "scoring_method": "Weighted average of available factors"
    }


if __name__ == "__main__":

    print("\nQUIKLEE LEAD QUALIFICATION ENGINE")
    print("=" * 55)

    # Illustrative scores, not actual company assessments.
    result = calculate_lead_score(
        shipping_potential=9,
        aov=8,
        cod_potential=7,
        growth=9,
        ecommerce_relevance=10,
        company_scale=8
    )

    for key, value in result.items():
        print(f"{key}: {value}")
