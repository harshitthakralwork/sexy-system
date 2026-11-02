from __future__ import annotations

from app.shared.scoring import Operator, ScoringRule, evaluate

WEBSITE_RULES = [
    ScoringRule("No website", "website_status", 40, Operator.EQ, "missing", is_required=False),
    ScoringRule("Outdated theme signal", "website_is_wordpress_default", 15, Operator.EQ, True),
    ScoringRule("Has phone", "has_phone", 15, Operator.EQ, True),
    ScoringRule("Has email", "has_email", 15, Operator.EQ, True),
    ScoringRule("Local services category", "category_is_local_service", 15, Operator.EQ, True),
]


def test_full_score_when_every_signal_fires() -> None:
    signals = {
        "website_status": "missing",
        "website_is_wordpress_default": True,
        "has_phone": True,
        "has_email": True,
        "category_is_local_service": True,
    }
    result = evaluate(signals, WEBSITE_RULES, qualification_threshold=60)
    assert result.score == 100.0
    assert result.qualified is True
    assert result.confidence == 100.0
    assert result.missing_signals == []


def test_score_is_weighted_not_binary() -> None:
    # Only the 40-weight "no website" signal fires.
    result = evaluate({"website_status": "missing"}, WEBSITE_RULES, qualification_threshold=60)
    assert result.score == 40.0
    assert result.qualified is False


def test_evidence_explains_each_contribution() -> None:
    result = evaluate({"website_status": "missing", "has_phone": True}, WEBSITE_RULES)
    contributions = {e.rule_name: e.score_contribution for e in result.evidence}
    assert contributions["No website"] == 40
    assert contributions["Has phone"] == 15
    assert contributions["Has email"] == 0


def test_unobserved_signals_lower_confidence_and_are_listed() -> None:
    result = evaluate({"website_status": "missing"}, WEBSITE_RULES)
    # Only one of five signals has data; the score must not claim certainty.
    assert result.confidence == 20.0
    assert "has_email" in result.missing_signals


def test_missing_required_signal_blocks_qualification_even_at_high_score() -> None:
    rules = [
        ScoringRule("Must have contact", "has_email", 90, Operator.EQ, True, is_required=True),
        ScoringRule("No website", "website_status", 10, Operator.EQ, "missing"),
    ]
    result = evaluate({"website_status": "missing"}, rules, qualification_threshold=50)
    assert result.score == 10.0
    assert result.qualified is False
    assert result.unmet_required_signals == ["has_email"]


def test_exists_operator_treats_empty_values_as_absent() -> None:
    rules = [ScoringRule("Has description", "description", 10, Operator.EXISTS)]
    assert evaluate({"description": ""}, rules).score == 0.0
    assert evaluate({"description": "Cafe in Indiranagar"}, rules).score == 100.0
    assert evaluate({"description": None}, rules).confidence == 0.0


def test_missing_operator_fires_when_value_is_absent() -> None:
    rules = [ScoringRule("No social profile", "instagram_url", 10, Operator.MISSING)]
    assert evaluate({}, rules).score == 100.0
    assert evaluate({"instagram_url": "https://instagram.com/x"}, rules).score == 0.0


def test_numeric_thresholds_gte_and_lte() -> None:
    rules = [ScoringRule("High rating", "google_rating", 10, Operator.GTE, 4.2)]
    assert evaluate({"google_rating": 4.5}, rules).score == 100.0
    assert evaluate({"google_rating": 4.0}, rules).score == 0.0

    inverse = [ScoringRule("Low traffic", "site_monthly_visits", 10, Operator.LTE, 1000)]
    assert evaluate({"site_monthly_visits": 500}, inverse).score == 100.0


def test_contains_is_case_insensitive_substring() -> None:
    rules = [ScoringRule("Mentions delivery", "description", 10, Operator.CONTAINS, "delivery")]
    assert evaluate({"description": "Home Delivery available"}, rules).score == 100.0
    assert evaluate({"description": "Dine-in only"}, rules).score == 0.0


def test_inactive_rules_are_ignored_entirely() -> None:
    rules = [
        ScoringRule("Live", "has_phone", 50, Operator.EQ, True),
        ScoringRule("Retired", "website_status", 50, Operator.EQ, "missing", is_active=False),
    ]
    result = evaluate({"has_phone": True}, rules)
    assert result.score == 100.0
    assert [e.rule_name for e in result.evidence] == ["Live"]


def test_empty_rule_set_yields_zero_not_crash() -> None:
    result = evaluate({"has_phone": True}, [])
    assert result.score == 0.0
    assert result.qualified is False
    assert result.confidence == 0.0


def test_evaluation_is_reproducible_from_the_same_inputs() -> None:
    signals = {"website_status": "missing", "has_email": True, "has_phone": True}
    first = evaluate(signals, WEBSITE_RULES, qualification_threshold=70, profile_version=3)
    second = evaluate(signals, WEBSITE_RULES, qualification_threshold=70, profile_version=3)
    assert first.score == second.score
    assert first.profile_version == 3
    assert [e.description for e in first.evidence] == [e.description for e in second.evidence]
