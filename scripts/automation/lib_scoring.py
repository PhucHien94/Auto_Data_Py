#!/usr/bin/env python3
"""
Shared scoring logic for the golden test-set pipeline (test strategy Part 3).

Implements the 4-tier pass model:
  Tier 1 - exact Top-1 match
  Tier 2 - expected_top1 present anywhere in actual_topN
  Tier 3 - recall against acceptable_set clears --tier3-threshold
  Tier 4 - none of the above -> flagged for manual review

Pure functions, no network/file I/O, so this can be unit-tested and reused by
runner_autocomplete.py, run_autoscript.py, and score_and_report.py alike.
"""
from statistics import median


def score_search_row(expected_top1, acceptable_set, actual_topn, tier3_threshold=0.5):
    """Return (tier:int, recall:float) for one search-result test row."""
    acceptable_set = acceptable_set or ([expected_top1] if expected_top1 else [])
    actual_topn = actual_topn or []

    if actual_topn and expected_top1 is not None and actual_topn[0] == expected_top1:
        return 1, 1.0

    if expected_top1 is not None and expected_top1 in actual_topn:
        return 2, 1.0

    if acceptable_set:
        hit = len(set(actual_topn) & set(acceptable_set))
        recall = hit / len(acceptable_set)
        if recall >= tier3_threshold:
            return 3, recall
        return 4, recall

    return 4, 0.0


def score_autocomplete_row(expected_suggestions, actual_suggestions, tier3_threshold=0.5):
    """expected_suggestions: [{'keyword','rank'}]; actual_suggestions: [str, ...]."""
    expected_keywords = [s["keyword"].lower() for s in (expected_suggestions or [])]
    actual_lower = [s.lower() for s in (actual_suggestions or [])]

    if not expected_keywords:
        return 4, 0.0
    if actual_lower and actual_lower[0] == expected_keywords[0]:
        return 1, 1.0
    if expected_keywords[0] in actual_lower:
        return 2, 1.0

    hit = len(set(actual_lower) & set(expected_keywords))
    recall = hit / len(expected_keywords)
    if recall >= tier3_threshold:
        return 3, recall
    return 4, recall


def summarize_repeats(tiers, pass_tier=3):
    """tiers: list of per-call tier ints (1 = best ... 4 = worst) for the SAME keyword,
    captured from N separate actual-output calls. Returns a matching-ratio summary
    answering "how often did this keyword's actual output match the expected output",
    not just "did it match once"."""
    n = len(tiers)
    if n == 0:
        return {"repeat_n": 0, "matching_ratio": None, "best_tier": None, "worst_tier": None, "stable": None}
    matches = sum(1 for t in tiers if t <= pass_tier)
    return {
        "repeat_n": n,
        "matching_ratio": round(matches / n, 3),
        "best_tier": min(tiers),
        "worst_tier": max(tiers),
        "stable": len(set(tiers)) == 1,
    }


def reciprocal_rank(expected_top1, actual_topn):
    if not expected_top1 or not actual_topn:
        return 0.0
    if expected_top1 in actual_topn:
        return 1.0 / (actual_topn.index(expected_top1) + 1)
    return 0.0


def aggregate_metrics(rows):
    """rows: list of dicts with tier, recall, mrr, latency_ms, actual_topn (post-scoring)."""
    n = len(rows)
    if n == 0:
        return {}
    tier1 = sum(1 for r in rows if r["tier"] == 1)
    tier2 = sum(1 for r in rows if r["tier"] <= 2)
    tier3 = sum(1 for r in rows if r["tier"] <= 3)
    zero_result = sum(1 for r in rows if not r.get("actual_topn"))
    latencies = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)

    def pct(v):
        return round(100.0 * v / n, 1)

    def p_at(sorted_vals, pct_):
        if not sorted_vals:
            return None
        idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * pct_))
        return sorted_vals[idx]

    ratios = [r["matching_ratio"] for r in rows if r.get("matching_ratio") is not None]
    unstable = sum(1 for r in rows if r.get("stable_across_repeats") is False)

    return {
        "n": n,
        "precision_at_1_pct": pct(tier1),
        "recall_tier2_pct": pct(tier2),
        "recall_tier3_pct": pct(tier3),
        "mrr": round(sum(r.get("mrr", 0.0) for r in rows) / n, 3),
        "zero_result_pct": pct(zero_result),
        "latency_p50_ms": p_at(latencies, 0.50),
        "latency_p95_ms": p_at(latencies, 0.95),
        "latency_median_ms": round(median(latencies), 1) if latencies else None,
        "tier4_count": sum(1 for r in rows if r["tier"] == 4),
        "avg_matching_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
        "unstable_count": unstable if ratios else None,
    }
