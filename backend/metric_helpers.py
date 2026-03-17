"""Pure metric helpers shared across backend and Modal read routes."""

from __future__ import annotations


def logistic(x: float, x0: float, k: float) -> float:
    import math

    return 1 / (1 + math.exp(-k * (x - x0)))


def compute_risk_wlc(
    inspections: list,
    permits: list,
    licenses: list,
    news: list,
    politics: list,
    reviews: list | None = None,
) -> float:
    weights = {
        "regulatory": 0.25,
        "market": 0.20,
        "economic": 0.20,
        "accessibility": 0.15,
        "political": 0.10,
        "community": 0.10,
    }

    scored: list[tuple[str, float, float]] = []

    total_inspections = len(inspections)
    if total_inspections > 0:
        failed = sum(
            1
            for inspection in inspections
            if inspection.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business")
        )
        fail_rate = failed / total_inspections
        scored.append(("regulatory", logistic(fail_rate, 0.22, 8), weights["regulatory"]))

    license_count = len(licenses)
    if license_count > 0:
        scored.append(("market", logistic(license_count, 12, 0.25), weights["market"] * 0.5))

    ratings = [
        review.get("metadata", {}).get("rating", 0)
        for review in (reviews or [])
        if review.get("metadata", {}).get("rating")
    ]
    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        scored.append(("market", 1 - logistic(avg_rating, 3.5, 3), weights["market"] * 0.5))

    permit_count = len(permits)
    if permit_count > 0:
        scored.append(("economic", 1 - logistic(permit_count, 8, 0.3), weights["economic"]))

    if politics:
        scored.append(("political", logistic(len(politics), 5, 0.4), weights["political"]))

    if news:
        scored.append(("community", 1 - logistic(len(news), 8, 0.3), weights["community"]))

    if not scored:
        return 5.0

    weighted_risk = sum(risk * weight for _, risk, weight in scored)
    total_weight = sum(weight for _, _, weight in scored)
    normalized = weighted_risk / total_weight
    return round(normalized * 10, 1)


def compute_metrics(
    name: str,
    inspections: list,
    permits: list,
    licenses: list,
    news: list,
    politics: list,
    reviews: list | None = None,
) -> dict:
    total_inspections = len(inspections)
    regulatory_density = min(100, total_inspections * 5) if total_inspections > 0 else 0
    business_activity = min(100, len(licenses) * 8) if licenses else 0
    risk_score = compute_risk_wlc(inspections, permits, licenses, news, politics, reviews)
    sentiment = min(100, len(news) * 10) if news else 0

    ratings = [
        review.get("metadata", {}).get("rating", 0)
        for review in (reviews or [])
        if review.get("metadata", {}).get("rating")
    ]
    avg_review_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    return {
        "neighborhood": name,
        "regulatory_density": round(regulatory_density, 1),
        "business_activity": round(business_activity, 1),
        "sentiment": round(sentiment, 1),
        "risk_score": risk_score,
        "active_permits": len(permits),
        "news_mentions": len(news),
        "avg_review_rating": avg_review_rating,
        "review_count": len(ratings),
    }
