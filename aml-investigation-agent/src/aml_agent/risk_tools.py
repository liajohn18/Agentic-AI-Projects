"""Deterministic, explainable risk calculations for the AML demo."""

from decimal import Decimal

from schemas import AMLTransaction, Customer, RiskAssessment


def assess_transaction(transaction: AMLTransaction, customer: Customer) -> RiskAssessment:
    """Return an illustrative score from transparent demo rules.

    This is not a calibrated production model or a legal determination.
    """
    score = 0.10
    indicators: list[str] = []

    if transaction.amount > Decimal("10000"):
        score += 0.35
        indicators.append("Transaction exceeds the demo review threshold")

    if transaction.channel == "cash":
        score += 0.25
        indicators.append("Transaction uses the cash channel")

    if customer.risk_rating == "high":
        score += 0.15
        indicators.append("Customer has a high KYC risk rating")

    monthly_turnover = customer.expected_monthly_turnover_usd
    if monthly_turnover and monthly_turnover > 0:
        ratio = transaction.amount / monthly_turnover
        if ratio >= Decimal("0.50"):
            score += 0.20
            indicators.append(
                "Transaction is at least half of expected monthly turnover"
            )

    if (customer.pep_status or "").casefold() in {"potential_match", "possible_match"}:
        score += 0.10
        indicators.append("Potential PEP screening match needs verification")

    if (customer.sanctions_screening_status or "").casefold() in {
        "potential_match",
        "possible_match",
    }:
        score += 0.20
        indicators.append("Potential sanctions screening match needs verification")

    score = min(score, 1.0)
    if score >= 0.70:
        level = "high"
    elif score >= 0.40:
        level = "medium"
    else:
        level = "low"

    return RiskAssessment(
        risk_score=score,
        risk_level=level,
        indicators=indicators,
        rationale=(
            "Illustrative score from explicit demo rules using transaction "
            "amount, channel, KYC risk rating, turnover ratio, and screening "
            "status. Human verification is required for screening matches."
        ),
    )
