"""Paired statistics and measured-versus-proxy outcome summaries."""
from __future__ import annotations
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from typing import Any
from .evaluation_contracts import _mapping, _sequence, _is_number

def _measured_values(runs: Sequence[Mapping[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for record in runs:
        measurement = _mapping(record.get(metric))
        if measurement and measurement.get("provenance") == "observed" and _is_number(measurement.get("value")):
            values.append(float(measurement["value"]))
    return values


def _rate(runs: Sequence[Mapping[str, Any]], field: str) -> float:
    if not runs:
        return 0.0
    return sum(bool(record.get(field)) for record in runs) / len(runs)


def summarize_arm(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize recorded outcomes without upgrading proxies into measurements."""

    records = list(runs)
    qualities = [float(record["quality"]) for record in records if _is_number(record.get("quality"))]
    costs = _measured_values(records, "cost")
    latencies = _measured_values(records, "latency")
    proxy_only = bool(records) and not costs and not latencies
    estimated = any(
        (_mapping(record.get(metric)) or {}).get("provenance") == "estimated"
        for record in records for metric in ("cost", "latency")
    )
    return {
        "run_count": len(records),
        "mean_quality": round(statistics.fmean(qualities), 6) if qualities else None,
        "median_cost": round(statistics.median(costs), 6) if costs else None,
        "median_latency": round(statistics.median(latencies), 6) if latencies else None,
        "pass_rate": round(sum(record.get("passed") is True for record in records) / len(records), 6) if records else 0.0,
        "proxy_only": proxy_only,
        "cost_claim": "measured" if costs else ("estimated-nonclaiming" if estimated else "unavailable"),
        "proxy_medians": {
            field: round(statistics.median([record.get("proxies", {}).get(field, 0) for record in records]), 6) if records else 0.0
            for field in ("model_calls", "spawn_count", "tool_calls", "question_count")
        },
        "unnecessary_spawn_rate": round(_rate(records, "unnecessary_spawn"), 6),
        "premise_reset_rate": round(_rate(records, "premise_reset"), 6),
        "repeated_settled_question_rate": round(_rate(records, "repeated_settled_question"), 6),
    }


def _paired_records(
    baseline: Sequence[Mapping[str, Any]], candidate: Sequence[Mapping[str, Any]]
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    baseline_by_key = {
        (str(record.get("scenario_id")), int(record.get("replicate_id", -1))): record for record in baseline
    }
    candidate_by_key = {
        (str(record.get("scenario_id")), int(record.get("replicate_id", -1))): record for record in candidate
    }
    if set(baseline_by_key) != set(candidate_by_key):
        return []
    return [(baseline_by_key[key], candidate_by_key[key]) for key in sorted(baseline_by_key)]


def _bootstrap_interval(differences: Sequence[float], seed: int, samples: int = 5000) -> tuple[float, float]:
    if not differences:
        raise ValueError("bootstrap requires paired differences")
    if len(set(differences)) == 1:
        exact = round(float(differences[0]), 6)
        return exact, exact
    generator = random.Random(seed)
    count = len(differences)
    means = sorted(statistics.fmean(differences[generator.randrange(count)] for _ in range(count)) for _ in range(samples))
    lower = means[max(0, math.floor(0.025 * samples) - 1)]
    upper = means[min(samples - 1, math.ceil(0.975 * samples) - 1)]
    return round(lower, 6), round(upper, 6)


def _bootstrap_statistic_interval(
    count: int,
    seed: int,
    statistic,
    samples: int = 5000,
) -> tuple[float, float]:
    if count < 1:
        raise ValueError("bootstrap requires paired observations")
    generator = random.Random(seed)
    values = sorted(statistic([generator.randrange(count) for _ in range(count)]) for _ in range(samples))
    lower = values[max(0, math.floor(0.025 * samples) - 1)]
    upper = values[min(samples - 1, math.ceil(0.975 * samples) - 1)]
    return (
        round(lower, 6) if math.isfinite(lower) else lower,
        round(upper, 6) if math.isfinite(upper) else upper,
    )


def _relative_median_change(baseline: Sequence[float], candidate: Sequence[float]) -> float:
    baseline_median = statistics.median(baseline)
    candidate_median = statistics.median(candidate)
    if baseline_median == 0:
        return 0.0 if candidate_median == 0 else math.inf
    return candidate_median / baseline_median - 1.0


def _simple_metric_gate(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], metric: str, margin: float, seed: int
) -> dict[str, Any]:
    simple = [pair for pair in pairs if pair[0].get("category") in {"direct", "simple", "direct-fast-path", "no-delegation-trap"}]
    if not simple:
        return {"status": "not-applicable", "claim_allowed": False, "change": None}
    baseline_values = _measured_values([pair[0] for pair in simple], metric)
    candidate_values = _measured_values([pair[1] for pair in simple], metric)
    if len(baseline_values) == len(simple) and len(candidate_values) == len(simple):
        baseline_median = statistics.median(baseline_values)
        candidate_median = statistics.median(candidate_values)
        change = _relative_median_change(baseline_values, candidate_values)
        lower, upper = _bootstrap_statistic_interval(
            len(simple),
            seed,
            lambda indexes: _relative_median_change(
                [baseline_values[index] for index in indexes],
                [candidate_values[index] for index in indexes],
            ),
        )
        status = "fail" if lower > margin + 1e-12 else ("pass" if upper <= margin + 1e-12 else "inconclusive")
        return {
            "status": status,
            "claim_allowed": status != "inconclusive",
            "change": round(change, 6) if math.isfinite(change) else "infinite",
            "baseline_median": round(baseline_median, 6),
            "candidate_median": round(candidate_median, 6),
            "confidence_interval": {"level": 0.95, "lower": lower, "upper": upper, "method": "paired-bootstrap"},
        }
    proxy_fields = ("model_calls", "spawn_count", "tool_calls", "question_count")
    proxy_changes = {
        field: statistics.median([pair[1].get("proxies", {}).get(field, 0) for pair in simple])
        - statistics.median([pair[0].get("proxies", {}).get(field, 0) for pair in simple])
        for field in proxy_fields
    }
    regressed = any(change > 0 for change in proxy_changes.values())
    return {
        "status": "fail" if regressed else "proxy-only",
        "claim_allowed": False,
        "change": None,
        "proxy_changes": proxy_changes,
        "reason": "measurement unavailable; proxies are labelled and cannot support a cost or latency claim",
    }


def _high_value_gate(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    quality_margin: float,
    time_margin: float,
    quality_noninferior: bool,
    seed: int,
) -> dict[str, Any]:
    selected = [
        pair for pair in pairs
        if "high-value-delegation" in (_sequence(pair[0].get("evaluation_groups")) or ())
        and "high-value-delegation" in (_sequence(pair[1].get("evaluation_groups")) or ())
    ]
    if not selected:
        return {
            "status": "fail",
            "quality_gain": None,
            "critical_path_reduction": None,
            "reason": "required bound high-value evaluation group evidence is absent",
        }
    quality_differences = [float(candidate["quality"]) - float(baseline["quality"]) for baseline, candidate in selected]
    quality_gain = statistics.fmean(quality_differences)
    quality_lower, quality_upper = _bootstrap_interval(quality_differences, seed)
    quality_status = (
        "pass"
        if quality_lower + 1e-12 >= quality_margin
        else ("fail" if quality_upper + 1e-12 < quality_margin else "inconclusive")
    )
    baseline_paths = _measured_values([pair[0] for pair in selected], "critical_path")
    candidate_paths = _measured_values([pair[1] for pair in selected], "critical_path")
    reduction: float | None = None
    time_interval: dict[str, Any] | None = None
    time_status = "not-applicable"
    if len(baseline_paths) == len(selected) and len(candidate_paths) == len(selected):
        base_median = statistics.median(baseline_paths)
        candidate_median = statistics.median(candidate_paths)
        if base_median > 0:
            reduction = (base_median - candidate_median) / base_median
            time_lower, time_upper = _bootstrap_statistic_interval(
                len(selected),
                seed + 1,
                lambda indexes: -_relative_median_change(
                    [baseline_paths[index] for index in indexes],
                    [candidate_paths[index] for index in indexes],
                ),
            )
            time_interval = {"level": 0.95, "lower": time_lower, "upper": time_upper, "method": "paired-bootstrap"}
            time_status = (
                "pass"
                if time_lower + 1e-12 >= time_margin
                else ("fail" if time_upper + 1e-12 < time_margin else "inconclusive")
            )
    if not quality_noninferior:
        status = "fail"
    elif "pass" in {quality_status, time_status}:
        status = "pass"
    elif "inconclusive" in {quality_status, time_status}:
        status = "inconclusive"
    else:
        status = "fail"
    return {
        "status": status,
        "quality_gain": round(quality_gain, 6),
        "quality_status": quality_status,
        "quality_confidence_interval": {
            "level": 0.95,
            "lower": quality_lower,
            "upper": quality_upper,
            "method": "paired-bootstrap",
        },
        "critical_path_reduction": round(reduction, 6) if reduction is not None else None,
        "critical_path_status": time_status,
        "critical_path_confidence_interval": time_interval,
    }


def _invalid_comparison(errors: Sequence[str]) -> dict[str, Any]:
    return {
        "status": "fail",
        "errors": list(errors),
        "quality_difference": None,
        "confidence_interval": {"level": 0.95, "lower": None, "upper": None},
        "quality_noninferiority": {"status": "fail"},
        "simple_tasks": {},
        "high_value_delegation": {"status": "fail"},
    }
