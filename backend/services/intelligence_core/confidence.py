from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS = {
    "source_reliability": 0.24,
    "freshness": 0.18,
    "location_certainty": 0.14,
    "timestamp_certainty": 0.10,
    "independent_confirmation": 0.18,
    "source_independence": 0.08,
    "cross_source_agreement": 0.08,
}


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def score_confidence(factors: dict[str, Any], weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or DEFAULT_WEIGHTS
    normalized = {k: _clamp(float(factors.get(k, 0.5))) for k in weights}
    denom = sum(max(0.0, w) for w in weights.values()) or 1.0
    score = sum(normalized[k] * max(0.0, weights[k]) for k in weights) / denom
    label = "very_high" if score >= 0.9 else "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return {"score": round(score, 4), "percent": round(score * 100, 1), "label": label, "factors": normalized}


def evaluate_calibration(samples: list[dict[str, Any]], bins: int = 10) -> dict[str, Any]:
    """Evaluate probability calibration without changing the scoring model.

    Each sample is {"predicted": 0..1, "actual": bool|0|1}. Returns Brier
    score and reliability bins so future weight tuning can be evidence-based.
    """
    bins = max(2, min(int(bins), 50))
    cleaned: list[tuple[float, float]] = []
    for item in samples[:100_000]:
        if not isinstance(item, dict):
            continue
        try:
            predicted = _clamp(float(item.get("predicted")))
            actual = 1.0 if bool(item.get("actual")) else 0.0
        except (TypeError, ValueError):
            continue
        cleaned.append((predicted, actual))
    if not cleaned:
        return {"count": 0, "brier_score": None, "bins": []}
    brier = sum((p - y) ** 2 for p, y in cleaned) / len(cleaned)
    bucketed: list[dict[str, Any]] = []
    for index in range(bins):
        lo, hi = index / bins, (index + 1) / bins
        subset = [(p, y) for p, y in cleaned if lo <= p < hi or (index == bins - 1 and p == 1.0)]
        if not subset:
            continue
        bucketed.append({
            "lower": round(lo, 3),
            "upper": round(hi, 3),
            "count": len(subset),
            "mean_predicted": round(sum(p for p, _ in subset) / len(subset), 4),
            "observed_rate": round(sum(y for _, y in subset) / len(subset), 4),
        })
    return {"count": len(cleaned), "brier_score": round(brier, 6), "bins": bucketed}
