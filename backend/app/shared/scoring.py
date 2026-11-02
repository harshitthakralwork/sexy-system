from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Operator(StrEnum):
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"
    EXISTS = "exists"
    MISSING = "missing"
    CONTAINS = "contains"
    IN = "in"


@dataclass(frozen=True)
class ScoringRule:
    """One signal that contributes to a service opportunity score.

    Mirrors the ``scoring_rules`` table: a signal key, a weight, an optional
    required flag, and the comparison to perform against observed data.
    """

    rule_name: str
    signal_key: str
    weight: float
    operator: Operator = Operator.EXISTS
    threshold: Any = None
    is_required: bool = False
    is_active: bool = True


@dataclass(frozen=True)
class Evidence:
    """Why a rule did or did not contribute, in the user's terms."""

    rule_name: str
    signal_key: str
    description: str
    observed_value: Any
    score_contribution: float
    satisfied: bool


@dataclass(frozen=True)
class ScoreResult:
    score: float
    max_score: float
    confidence: float
    qualified: bool
    profile_version: int
    evidence: list[Evidence] = field(default_factory=list)
    missing_signals: list[str] = field(default_factory=list)
    unmet_required_signals: list[str] = field(default_factory=list)


def _compare(rule: ScoringRule, observed: Any) -> bool:
    if rule.operator is Operator.EXISTS:
        return observed not in (None, "", [], {}, set())
    if rule.operator is Operator.MISSING:
        return observed in (None, "", [], {}, set())
    if observed is None:
        return False
    if rule.operator is Operator.EQ:
        return observed == rule.threshold
    if rule.operator is Operator.NEQ:
        return observed != rule.threshold
    if rule.operator is Operator.IN:
        return observed in (rule.threshold or ())
    if rule.operator is Operator.CONTAINS:
        haystack = observed if isinstance(observed, str) else str(observed)
        return str(rule.threshold).lower() in haystack.lower()
    try:
        left = float(observed)
        right = float(rule.threshold)
    except (TypeError, ValueError):
        return False
    if rule.operator is Operator.GTE:
        return left >= right
    if rule.operator is Operator.LTE:
        return left <= right
    return False


def evaluate(
    signals: dict[str, Any],
    rules: list[ScoringRule],
    *,
    qualification_threshold: float = 60.0,
    profile_version: int = 1,
) -> ScoreResult:
    """Deterministic opportunity scoring.

    Score is the weighted share of satisfied rules, normalised to 0-100, so it
    is reproducible from the stored rule set and observed signals. No model
    judgement is involved: AI may explain a score later but may not create one.
    """
    active = [rule for rule in rules if rule.is_active]
    for rule in active:
        # The database refuses a negative weight; the evaluator must too, or a
        # rule loaded from somewhere else could push a score below zero and make
        # the published number meaningless.
        if not math.isfinite(rule.weight) or rule.weight < 0:
            raise ValueError(f"Rule '{rule.rule_name}' has an invalid weight: {rule.weight}")
    if not active:
        return ScoreResult(
            score=0.0,
            max_score=0.0,
            confidence=0.0,
            qualified=False,
            profile_version=profile_version,
            missing_signals=[],
        )

    evidence: list[Evidence] = []
    missing: list[str] = []
    unmet_required: list[str] = []
    total_weight = 0.0
    earned = 0.0

    for rule in active:
        observed = signals.get(rule.signal_key)
        known = observed is not None or rule.operator is Operator.MISSING
        if not known:
            missing.append(rule.signal_key)

        satisfied = _compare(rule, observed)
        contribution = round(rule.weight, 4) if satisfied else 0.0
        total_weight += rule.weight
        earned += contribution

        evidence.append(
            Evidence(
                rule_name=rule.rule_name,
                signal_key=rule.signal_key,
                description=_describe(rule, observed, satisfied),
                observed_value=observed,
                score_contribution=contribution,
                satisfied=satisfied,
            )
        )

        if rule.is_required and not satisfied:
            unmet_required.append(rule.signal_key)

    score = round((earned / total_weight) * 100, 2) if total_weight else 0.0
    observed_share = (len(active) - len(missing)) / len(active)
    qualified = score >= qualification_threshold and not unmet_required

    return ScoreResult(
        score=score,
        max_score=100.0,
        confidence=round(observed_share * 100, 2),
        qualified=qualified,
        profile_version=profile_version,
        evidence=evidence,
        missing_signals=missing,
        unmet_required_signals=unmet_required,
    )


def _describe(rule: ScoringRule, observed: Any, satisfied: bool) -> str:
    verb = "observed" if satisfied else "not satisfied"
    if observed is None:
        return f"{rule.rule_name}: no data for {rule.signal_key} ({verb})"
    return f"{rule.rule_name}: {rule.signal_key}={observed!r} ({verb})"
