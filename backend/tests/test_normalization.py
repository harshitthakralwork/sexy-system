from __future__ import annotations

from app.shared.normalization import (
    canonical_hash,
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
)


def test_email_is_lowered_and_whitespace_stripped() -> None:
    assert normalize_email("  Owner@SparkCoffee.IN ") == "owner@sparkcoffee.in"


def test_email_without_domain_is_rejected() -> None:
    assert normalize_email("not-an-email") is None
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_plus_addressing_is_preserved() -> None:
    # These may be genuinely different mailboxes; collapsing them loses data.
    assert normalize_email("a+b@example.com") == "a+b@example.com"


def test_indian_mobile_normalizes_to_e164() -> None:
    assert normalize_phone("098765 43210", "IN") == "+919876543210"
    assert normalize_phone("+91 98765-43210", "IN") == "+919876543210"


def test_local_number_needs_a_region_to_be_meaningful() -> None:
    assert normalize_phone("9876543210", "IN") == "+919876543210"
    # The same digits are not a valid US number; region is not cosmetic.
    assert normalize_phone("9876543210", "US") is None


def test_invalid_phone_returns_none_instead_of_guessing() -> None:
    assert normalize_phone("12", "IN") is None
    assert normalize_phone("not a phone", "IN") is None


def test_domain_reduces_to_registrable_domain() -> None:
    assert normalize_domain("https://Shop.Example.CO.uk/offers") == "example.co.uk"
    assert normalize_domain("blog.example.com") == "example.com"
    assert normalize_domain("example.com") == "example.com"


def test_subdomains_of_the_same_business_match() -> None:
    assert normalize_domain("https://www.sparkcoffee.in") == normalize_domain(
        "http://sparkcoffee.in/menu"
    )


def test_domain_of_garbage_is_none() -> None:
    assert normalize_domain(None) is None
    assert normalize_domain("not a url") is None


def test_name_normalization_drops_legal_suffixes_and_punctuation() -> None:
    assert normalize_name("Spark Coffee LLP") == "spark coffee"
    assert normalize_name("SPARK,  coffee pvt ltd") == "spark coffee"


def test_name_normalization_keeps_a_single_token_business() -> None:
    assert normalize_name("Zomato") == "zomato"


def test_hash_is_order_and_case_independent() -> None:
    a = canonical_hash("Spark Coffee", "sparkcoffee.in", "+919876543210")
    b = canonical_hash("spark coffee", "+919876543210", "SPARKCOFFEE.IN")
    assert a == b


def test_hash_ignores_empty_parts_but_distinguishes_real_content() -> None:
    with_blank = canonical_hash("Spark Coffee", None, "")
    different = canonical_hash("Spark Coffee", "sparkcoffee.in")
    assert with_blank != different


def test_hash_is_stable_across_calls() -> None:
    assert canonical_hash("x", "y") == canonical_hash("x", "y")
