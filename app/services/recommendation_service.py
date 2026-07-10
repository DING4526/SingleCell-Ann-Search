"""Shared recommendation labels for ANN benchmark and evaluation results."""
from __future__ import annotations

from statistics import median
import math
from typing import Any


RECALL_TOLERANCE = 1e-4
TIME_TOLERANCE_MS = 1e-4
SPEED_RECALL_MIN = 0.90
BALANCED_RECALL_MIN = 0.95
COMPACT_RECALL_MIN = 0.90
NOT_RECOMMENDED_RECALL = 0.80
COMPACT_MEDIAN_RATIO = 0.60


def _get(row: Any, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _row_id(row: Any):
    return _get(row, "id")


def _float(row: Any, key: str, default: float = 0.0) -> float:
    value = _get(row, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def quality_label(recall_at_k: float | None) -> str:
    recall = float(recall_at_k or 0.0)
    if recall >= BALANCED_RECALL_MIN:
        return "excellent"
    if recall >= SPEED_RECALL_MIN:
        return "acceptable"
    if recall >= NOT_RECOMMENDED_RECALL:
        return "low_recall"
    return "not_recommended"


def quality_gate(recall_at_k: float | None) -> str:
    recall = float(recall_at_k or 0.0)
    if recall >= BALANCED_RECALL_MIN:
        return "professional"
    if recall >= SPEED_RECALL_MIN:
        return "acceptable"
    if recall >= NOT_RECOMMENDED_RECALL:
        return "research_only"
    return "reject"


def assign_recommendation_tags(rows: list[Any]) -> dict[Any, list[str]]:
    """Assign comparable recommendation tags with ties preserved.

    Rows are expected to expose id, status, recall_at_k, avg_query_time_ms,
    p95_query_time_ms, and index_size_bytes attributes or dict keys.
    """
    successful = [row for row in rows if _get(row, "status", "success") == "success" and _row_id(row) is not None]
    labels: dict[Any, list[str]] = {_row_id(row): [] for row in successful}
    if not successful:
        return labels

    for row in successful:
        if _float(row, "recall_at_k") < NOT_RECOMMENDED_RECALL:
            labels[_row_id(row)].append("not_recommended")

    max_recall = max(_float(row, "recall_at_k") for row in successful)
    for row in successful:
        if max_recall - _float(row, "recall_at_k") <= RECALL_TOLERANCE:
            labels[_row_id(row)].append("best_recall")

    speed_candidates = [row for row in successful if _float(row, "recall_at_k") >= SPEED_RECALL_MIN]
    if speed_candidates:
        min_mean = min(_float(row, "avg_query_time_ms", 1e12) for row in speed_candidates)
        min_p95 = min(_float(row, "p95_query_time_ms", 1e12) for row in speed_candidates)
        for row in speed_candidates:
            mean_close = abs(_float(row, "avg_query_time_ms", 1e12) - min_mean) <= TIME_TOLERANCE_MS
            p95_close = abs(_float(row, "p95_query_time_ms", 1e12) - min_p95) <= TIME_TOLERANCE_MS
            if mean_close or p95_close:
                labels[_row_id(row)].append("best_speed")

    fastest = min(successful, key=lambda row: _float(row, "avg_query_time_ms", 1e12))
    if _float(fastest, "recall_at_k") < SPEED_RECALL_MIN:
        labels[_row_id(fastest)].append("fast_but_low_recall")

    balanced_candidates = [row for row in successful if _float(row, "recall_at_k") >= BALANCED_RECALL_MIN]
    if balanced_candidates:
        scores = {
            _row_id(row): _float(row, "recall_at_k") / max(_float(row, "avg_query_time_ms", 1e12), 1e-6)
            for row in balanced_candidates
        }
        best_score = max(scores.values())
        for row in balanced_candidates:
            if best_score - scores[_row_id(row)] <= RECALL_TOLERANCE:
                labels[_row_id(row)].append("best_balanced")

    sizes = [_float(row, "index_size_bytes", 0.0) for row in successful if _float(row, "index_size_bytes", 0.0) > 0]
    if len(sizes) >= 2:
        size_median = median(sizes)
        compact_cutoff = size_median * COMPACT_MEDIAN_RATIO
        for row in successful:
            size = _float(row, "index_size_bytes", 0.0)
            if size > 0 and size <= compact_cutoff and _float(row, "recall_at_k") >= COMPACT_RECALL_MIN:
                labels[_row_id(row)].append("compact")

    return labels


def tags_to_string(tags: list[str] | None) -> str | None:
    if not tags:
        return None
    return ",".join(dict.fromkeys(tags))


def _inverse_log_scores(rows: list[Any], key: str) -> dict[Any, float]:
    values = { _row_id(row): math.log1p(max(_float(row, key), 0.0)) for row in rows }
    if not values:
        return {}
    low = min(values.values())
    high = max(values.values())
    if high - low <= 1e-12:
        return {row_id: 1.0 for row_id in values}
    return {row_id: (high - value) / (high - low) for row_id, value in values.items()}


def _normalized_scores(rows: list[Any], key: str) -> dict[Any, float]:
    values = {_row_id(row): _float(row, key) for row in rows}
    if not values:
        return {}
    low = min(values.values())
    high = max(values.values())
    if high - low <= 1e-12:
        return {row_id: 1.0 for row_id in values}
    return {row_id: (value - low) / (high - low) for row_id, value in values.items()}


def assign_selection_recommendations(rows: list[Any]) -> tuple[dict[Any, list[str]], list[Any]]:
    """Recommend a deterministic 2-3 index shortlist for a completed experiment."""
    successful = [
        row for row in rows
        if _get(row, "status") == "success"
        and _row_id(row) is not None
        and _float(row, "recall_at_k") >= NOT_RECOMMENDED_RECALL
    ]
    labels: dict[Any, list[str]] = {_row_id(row): [] for row in successful}
    if not successful:
        return labels, []

    quality = sorted(
        successful,
        key=lambda row: (
            -_float(row, "recall_at_k"),
            _float(row, "p95_query_time_ms", 1e12),
            _float(row, "index_size_bytes", 1e18),
            _row_id(row),
        ),
    )[0]
    labels[_row_id(quality)].append("best_recall")

    speed_pool = [row for row in successful if _float(row, "recall_at_k") >= SPEED_RECALL_MIN]
    speed = None
    if speed_pool:
        speed = sorted(
            speed_pool,
            key=lambda row: (
                -_float(row, "speedup"),
                -_float(row, "recall_at_k"),
                _float(row, "index_size_bytes", 1e18),
                _row_id(row),
            ),
        )[0]
        labels[_row_id(speed)].append("best_speed")

    balanced_pool = [row for row in successful if _float(row, "recall_at_k") >= BALANCED_RECALL_MIN]
    balanced_degraded = False
    if not balanced_pool:
        balanced_pool = [row for row in successful if _float(row, "recall_at_k") >= SPEED_RECALL_MIN]
        balanced_degraded = bool(balanced_pool)

    balanced_ranking: list[Any] = []
    if balanced_pool:
        quality_scores = _normalized_scores(balanced_pool, "recall_at_k")
        latency_scores = _inverse_log_scores(balanced_pool, "p95_query_time_ms")
        size_scores = _inverse_log_scores(balanced_pool, "index_size_bytes")

        def balanced_score(row: Any) -> float:
            row_id = _row_id(row)
            return (
                0.50 * quality_scores.get(row_id, 0.0)
                + 0.35 * latency_scores.get(row_id, 0.0)
                + 0.15 * size_scores.get(row_id, 0.0)
            )

        balanced_ranking = sorted(
            balanced_pool,
            key=lambda row: (
                -balanced_score(row),
                -_float(row, "recall_at_k"),
                _float(row, "p95_query_time_ms", 1e12),
                _float(row, "index_size_bytes", 1e18),
                _row_id(row),
            ),
        )
        labels[_row_id(balanced_ranking[0])].append("best_balanced")
        if balanced_degraded:
            labels[_row_id(balanced_ranking[0])].append("acceptable_balanced")

    selected: list[Any] = []
    for row in [quality, speed, balanced_ranking[0] if balanced_ranking else None]:
        row_id = _row_id(row) if row is not None else None
        if row_id is not None and row_id not in selected:
            selected.append(row_id)

    if len(selected) < 2:
        fallback = balanced_ranking or sorted(
            successful,
            key=lambda row: (-_float(row, "recall_at_k"), -_float(row, "speedup"), _row_id(row)),
        )
        for row in fallback:
            if _row_id(row) not in selected:
                selected.append(_row_id(row))
            if len(selected) >= 2:
                break

    return labels, selected[:3]
