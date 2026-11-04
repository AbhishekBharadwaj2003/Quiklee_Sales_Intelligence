
from database.company_repository import (
    get_company_by_id,
    update_company
)

from database.research_repository import (
    get_company_research_history
)

from qualification.lead_scoring import calculate_lead_score


def qualify_company(company_id: int, business_inputs: dict):
    """Calculate and save a company's Quiklee qualification score."""

    company = get_company_by_id(company_id)

    if not company:
        raise ValueError(f"Company ID {company_id} not found.")

    # Retrieve existing research
    research_history = get_company_research_history(company_id)

    if not research_history:
        print("Warning: No research history found.")

    # Calculate qualification score
    result = calculate_lead_score(
        shipping_potential=business_inputs.get("shipping_potential"),
        aov=business_inputs.get("aov"),
        cod_potential=business_inputs.get("cod_potential"),
        growth=business_inputs.get("growth"),
        ecommerce_relevance=business_inputs.get("ecommerce_relevance"),
        company_scale=business_inputs.get("company_scale")
    )

    if result["lead_score"] is None:
        raise ValueError(
            "Insufficient information to calculate a qualification score."
        )

    # Save qualification result
    update_company(
        company_id,
        {
            "qualification_score": result["lead_score"],
            "qualification_category": result["lead_category"],
            "data_completeness": result["data_completeness"]
        }
    )

    return {
        "company_id": company_id,
        "company_name": company["company_name"],
        "research_records": len(research_history),
        **result
    }


if __name__ == "__main__":

    print("\nQUIKLEE COMPANY QUALIFICATION")
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

    company_id = int(input("\nEnter company ID: "))

    # Illustrative scores for testing only.
    # These must eventually come from verified research and
    # transparent business qualification rules.
    business_inputs = {
        "shipping_potential": 8,
        "aov": 7,
        "cod_potential": 6,
        "growth": 8,
        "ecommerce_relevance": 9,
        "company_scale": 7
    }

    result = qualify_company(
        company_id,
        business_inputs
    )

    print("\nQUALIFICATION RESULT")
    print("=" * 55)

    for key, value in result.items():
        print(f"{key}: {value}")
