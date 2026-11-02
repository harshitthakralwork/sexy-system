from __future__ import annotations

import hashlib
import re
import unicodedata

import phonenumbers
import tldextract
from phonenumbers.phonenumberutil import NumberParseException

_WHITESPACE = re.compile(r"\s+")
_NAME_NOISE = re.compile(r"[^\w\s&]", re.UNICODE)
# C0/C1 controls and zero-width characters. Scraped text is attacker-authored;
# control codes would survive into CSV exports and log lines, and zero-width
# characters make two visually identical strings compare differently.
_CONTROL_CHARS = re.compile(r"[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2060\ufeff]")

# Field widths from database-schema.md. Truncating here is deliberate: a 5 MB
# scraped page title that reaches an INSERT fails at the database with an
# opaque error, whereas here it is visibly clipped.
MAX_EMAIL_LENGTH = 320
MAX_PHONE_INPUT_LENGTH = 64
MAX_PHONE_LENGTH = 50
MAX_DOMAIN_LENGTH = 255
MAX_NAME_LENGTH = 255
MAX_ADDRESS_LENGTH = 2000
MAX_DESCRIPTION_LENGTH = 4000
MAX_URL_LENGTH = 2048

_TRAILING_LEGAL = {
    "ltd",
    "limited",
    "llp",
    "llc",
    "inc",
    "pvt",
    "private",
    "gmbh",
    "plc",
    "co",
    "company",
    "the",
}


def normalize_whitespace(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip()
    return _WHITESPACE.sub(" ", value)


def sanitize_text(value: object, *, max_length: int = MAX_NAME_LENGTH) -> str | None:
    """Clean scraped display text before it is stored or exported.

    Removes tag-shaped markup, control and zero-width characters, collapses
    whitespace and clips to a declared width. Web page titles are attacker
    content: without this they carry markup into every downstream surface —
    the CSV export, the business profile, and any future renderer.
    """
    if value is None:
        return None
    from app.shared.url_safety import strip_markup

    text = strip_markup(str(value)) or ""
    text = _CONTROL_CHARS.sub(" ", text)
    text = normalize_whitespace(text)
    if not text:
        return None
    return text[: max(max_length, 1)]


def normalize_email(value: str | None) -> str | None:
    """Lower-case the local part's domain and strip display noise.

    Plus-addressing is preserved: ``a+b@example.com`` and ``a@example.com`` may
    legitimately be different mailboxes for some providers.
    """
    if not value:
        return None
    candidate = value.strip().lower()
    # Prefix removal must be exact. lstrip() treats its argument as a character
    # set, so "mailto:" would eat leading o/w/n/e/r letters from real addresses.
    if candidate.startswith("mailto:"):
        candidate = candidate[len("mailto:") :].strip()
    candidate = _CONTROL_CHARS.sub("", candidate)
    if len(candidate) > MAX_EMAIL_LENGTH:
        return None
    if "@" not in candidate:
        return None
    local, _, domain = candidate.rpartition("@")
    if not local or not domain or "." not in domain:
        return None
    return f"{local}@{domain}"


def normalize_phone(value: str | None, default_region: str = "IN") -> str | None:
    """Return an E.164 number, or None when it is not parseable.

    Region-aware on purpose: a bare ``98765 43210`` is only meaningful with a
    country code, so the caller supplies the region it discovered the number in.
    """
    if not value:
        return None
    candidate = value.strip()
    if len(candidate) > MAX_PHONE_INPUT_LENGTH:
        # A megabyte of digits is not a phone number; do not hand it to a parser.
        return None
    try:
        parsed = phonenumbers.parse(candidate, default_region.upper())
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_domain(url_or_domain: str | None) -> str | None:
    """Reduce a URL to its registrable domain (eTLD+1).

    ``shop.example.co.uk`` and ``blog.example.co.uk`` collapse to
    ``example.co.uk``; ``example.com`` stays whole. This is what makes domain
    matching survive subdomains instead of producing false duplicates.
    """
    if not url_or_domain:
        return None
    candidate = url_or_domain.strip().lower()
    if len(candidate) > MAX_URL_LENGTH:
        return None
    extracted = tldextract.extract(candidate)
    if not extracted.domain or not extracted.suffix:
        return None
    return f"{extracted.domain}.{extracted.suffix}"


def normalize_name(value: str | None) -> str | None:
    """Canonical form used for fuzzy matching and duplicate keys.

    Lower-cased, punctuation removed, and trailing legal suffixes dropped so
    "Spark Coffee LLP" and "spark coffee" compare equal.
    """
    if not value:
        return None
    cleaned = _NAME_NOISE.sub(" ", normalize_whitespace(_CONTROL_CHARS.sub(" ", value)).lower())
    tokens = [t for t in cleaned.split() if t]
    while len(tokens) > 1 and tokens[-1] in _TRAILING_LEGAL:
        tokens.pop()
    result = " ".join(tokens)
    return result[:MAX_NAME_LENGTH] if result else None


def canonical_hash(*parts: str | None) -> str:
    """Stable fingerprint of the identifying parts of a record.

    Only non-empty parts contribute, and their order does not matter, so the
    same business reached through different sources produces the same hash.
    """
    significant = sorted({p.strip().lower() for p in parts if p and p.strip()})
    payload = "|".join(significant).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
