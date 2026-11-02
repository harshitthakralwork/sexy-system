from __future__ import annotations

from app.modules.deduplication.service import (
    Candidate,
    DedupKey,
    MatchClass,
    find_duplicates,
    partition,
)


def candidate(ref: str, **fields: str | None) -> Candidate:
    return Candidate(ref=ref, key=DedupKey(**fields))


def test_shared_domain_is_a_confirmed_duplicate() -> None:
    left = candidate("a", name="spark coffee", domain="sparkcoffee.in")
    right = candidate("b", name="Spark Coffee Roastery", domain="sparkcoffee.in")
    pair = find_duplicates([left, right])[0]
    assert pair.classification is MatchClass.CONFIRMED
    assert pair.auto_mergable is True
    assert "domain:sparkcoffee.in" in pair.reasons


def test_shared_phone_is_confirmed_even_with_different_names() -> None:
    left = candidate("a", name="Spark", phone="+919876543210")
    right = candidate("b", name="Different Name", phone="+919876543210")
    pair = find_duplicates([left, right])[0]
    assert pair.classification is MatchClass.CONFIRMED
    assert "phone:+919876543210" in pair.reasons


def test_similar_name_with_same_city_is_probable_not_confirmed() -> None:
    """Probable means a human decides. Auto-merging here would silently merge
    two real businesses that happen to share a name pattern."""
    left = candidate("a", name="spark coffee", city="bengaluru", address="100 feet road")
    right = candidate("b", name="spark coffe", city="bengaluru", address="100 feet rd")
    pair = find_duplicates([left, right])[0]
    assert pair.classification is MatchClass.PROBABLE
    assert pair.auto_mergable is False


def test_name_similarity_alone_is_only_possible() -> None:
    left = candidate("a", name="spark coffee")
    right = candidate("b", name="spark coffee")
    pair = find_duplicates([left, right])[0]
    assert pair.classification is MatchClass.POSSIBLE


def test_unrelated_records_produce_no_pair() -> None:
    left = candidate("a", name="spark coffee", domain="sparkcoffee.in")
    right = candidate("b", name="brew theory", domain="brewtheory.co.uk")
    assert find_duplicates([left, right]) == []


def test_partition_collapses_confirmed_and_keeps_review_backlog() -> None:
    a = candidate("a", name="Alpha", domain="alpha.test")
    b = candidate("b", name="Alpha Two", domain="alpha.test")
    c = candidate("c", name="Beta Cafe", city="bengaluru")
    d = candidate("d", name="Beta Cafee", city="bengaluru")

    pairs = find_duplicates([a, b, c, d])
    outcome = partition([a, b, c, d], pairs)

    assert outcome.merged_away == {"b": "a"}
    assert "a" in outcome.unique_refs and "b" not in outcome.unique_refs
    assert outcome.review_count == 1
    assert outcome.needs_review[0].classification is MatchClass.PROBABLE


def test_probable_pair_with_no_address_scores_on_name_not_on_missing_data() -> None:
    """0.95 similarity means "very likely the same business". Averaging in an
    absent address would have reported ~0.47 and misled the reviewer."""
    left = candidate("c", name="Beta Cafe", city="bengaluru")
    right = candidate("d", name="Beta Cafee", city="bengaluru")
    pair = find_duplicates([left, right])[0]
    assert pair.classification is MatchClass.PROBABLE
    assert pair.similarity > 0.9


def test_confirmed_chain_collapses_to_one_survivor() -> None:
    """a~b~c all share a domain; only one record must survive."""
    a = candidate("a", domain="chain.test")
    b = candidate("b", domain="chain.test")
    c = candidate("c", domain="chain.test")
    outcome = partition([a, b, c], find_duplicates([a, b, c]))
    assert outcome.unique_refs == ["a"]
    assert set(outcome.merged_away) == {"b", "c"}


def test_missing_signals_never_produce_false_matches() -> None:
    left = candidate("a")
    right = candidate("b")
    assert find_duplicates([left, right]) == []


def test_pairs_are_ordered_by_confidence() -> None:
    strong = candidate("a", domain="x.test")
    same = candidate("b", domain="x.test")
    weak = candidate("c", name="cafe del hi")
    weaker = candidate("d", name="cafe del ho")
    pairs = find_duplicates([strong, same, weak, weaker])
    assert pairs[0].classification is MatchClass.CONFIRMED
