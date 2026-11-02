"""Canonical observation keys used by the scoring engine.

Why this file exists: ``scoring_rules.signal_key`` is a free-form string in the
database, so without a defined vocabulary the Service Catalog UI would end up
inventing keys ad hoc and two rules would quietly mean different things. These
keys are the contract between enrichment (which produces observations) and
qualification (which consumes them).

Two rules every new signal must follow:

1. **A signal is an observation, not a claim about reality.** ``website_claimed``
   means "a source stated a website". ``website_reachable`` means "we fetched it
   and got a usable response". "This business has no website" is never a signal,
   because not finding one is not the same as there not being one
   (database-schema.md section 9.1).
2. **Absence is explicit.** ``None`` means "not observed". It is never coerced to
   ``False``, because the scoring engine reports missing signals and lowers
   confidence on them. Anything that silently defaults would inflate a score.
"""

from __future__ import annotations

from typing import Literal

SignalValue = bool | int | float | str | None

# --- Identity and contactability -------------------------------------------
NAME_PRESENT = "name_present"
DOMAIN_PRESENT = "domain_present"
PHONE_PRESENT = "phone_present"
EMAIL_PRESENT = "email_present"
ADDRESS_PRESENT = "address_present"
GEO_PRESENT = "geo_coordinates_present"
SOCIAL_PROFILE_COUNT = "social_profile_count"
CONTACT_PERSON_PRESENT = "contact_person_present"

# --- Web presence. Deliberately split so "unknown" survives. ---------------
WEBSITE_CLAIMED = "website_claimed"
WEBSITE_CHECKED = "website_checked"
WEBSITE_REACHABLE = "website_reachable"
WEBSITE_HAS_TITLE = "website_has_title"
WEBSITE_HAS_CMS_SIGNATURE = "website_has_cms_signature"
WEBSITE_LAST_MODIFIED_AGE_DAYS = "website_last_modified_age_days"
WEBSITE_HAS_CONTACT_PAGE = "website_has_contact_page"
WEBSITE_SECURED = "website_secured"

# --- Business activity -------------------------------------------------------
CATEGORY_MATCHED = "category_matched"
OPENING_HOURS_PRESENT = "opening_hours_present"
RATING = "rating"
REVIEW_COUNT = "review_count"
PRICE_LEVEL_PRESENT = "price_level_present"

# --- Freshness ---------------------------------------------------------------
DAYS_SINCE_LAST_RESEARCH = "days_since_last_research"
SOURCE_RECORD_COUNT = "source_record_count"

IDENTITY_SIGNALS = (
    NAME_PRESENT,
    DOMAIN_PRESENT,
    PHONE_PRESENT,
    EMAIL_PRESENT,
    ADDRESS_PRESENT,
    GEO_PRESENT,
    SOCIAL_PROFILE_COUNT,
    CONTACT_PERSON_PRESENT,
)

WEBSITE_SIGNALS = (
    WEBSITE_CLAIMED,
    WEBSITE_CHECKED,
    WEBSITE_REACHABLE,
    WEBSITE_HAS_TITLE,
    WEBSITE_HAS_CMS_SIGNATURE,
    WEBSITE_LAST_MODIFIED_AGE_DAYS,
    WEBSITE_HAS_CONTACT_PAGE,
    WEBSITE_SECURED,
)

ACTIVITY_SIGNALS = (
    CATEGORY_MATCHED,
    OPENING_HOURS_PRESENT,
    RATING,
    REVIEW_COUNT,
    PRICE_LEVEL_PRESENT,
)

FRESHNESS_SIGNALS = (DAYS_SINCE_LAST_RESEARCH, SOURCE_RECORD_COUNT)

ALL_SIGNALS = IDENTITY_SIGNALS + WEBSITE_SIGNALS + ACTIVITY_SIGNALS + FRESHNESS_SIGNALS

WebsiteStatusName = Literal["available", "missing", "inaccessible", "unknown"]


def derive_website_status(signals: dict[str, SignalValue]) -> WebsiteStatusName:
    """Map observations onto the four states the schema allows.

    Anything that has not actually been fetched stays ``unknown``. That is the
    difference between a lead database and a guess database.
    """
    if not signals.get(WEBSITE_CHECKED):
        return "unknown"
    if signals.get(WEBSITE_CLAIMED):
        return "available" if signals.get(WEBSITE_REACHABLE) else "inaccessible"
    # Checked and no URL was ever stated: the source record lacks a website,
    # which is the closest honest reading of "missing".
    return "missing"
