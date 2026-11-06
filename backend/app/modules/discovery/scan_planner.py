from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

COMMON_NICHE_ALIASES: dict[str, list[str]] = {
    "plumber": ["plumbers", "plumbing services", "sanitary repair", "pipe repair"],
    "plumbers": ["plumber", "plumbing services", "sanitary repair", "pipe repair"],
    "dentist": ["dentists", "dental clinic", "dental hospital", "orthodontist", "teeth care"],
    "dentists": ["dentist", "dental clinic", "dental hospital", "orthodontist", "teeth care"],
    "electrician": [
        "electricians",
        "electrical contractor",
        "electrical services",
        "wiring repair",
    ],
    "electricians": [
        "electrician",
        "electrical contractor",
        "electrical services",
        "wiring repair",
    ],
    "clinic": ["clinics", "medical centre", "health centre", "doctor clinic", "polyclinic"],
    "clinics": ["clinic", "medical centre", "health centre", "doctor clinic", "polyclinic"],
    "hospital": ["hospitals", "nursing home", "healthcare centre", "medical hospital"],
    "hospitals": ["hospital", "nursing home", "healthcare centre", "medical hospital"],
    "interior designer": [
        "interior designers",
        "interior decorator",
        "home interior design",
        "architectural interior",
    ],
    "interior designers": [
        "interior designer",
        "interior decorator",
        "home interior design",
        "architectural interior",
    ],
    "restaurant": ["restaurants", "dining", "eatery", "food cafe"],
    "restaurants": ["restaurant", "dining", "eatery", "food cafe"],
    "gym": ["gyms", "fitness center", "health club", "crossfit gym"],
    "gyms": ["gym", "fitness center", "health club", "crossfit gym"],
    "salon": ["salons", "beauty parlour", "hair salon", "barber shop"],
    "salons": ["salon", "beauty parlour", "hair salon", "barber shop"],
    "spa": ["spas", "wellness center", "massage centre", "ayurvedic spa"],
    "spas": ["spa", "wellness center", "massage centre", "ayurvedic spa"],
    "car repair": ["car service", "auto garage", "mechanic workshop", "auto repair"],
    "real estate": [
        "real estate agents",
        "property dealers",
        "property consultants",
        "real estate brokers",
    ],
    "accounting": ["CA firms", "chartered accountants", "tax consultants", "auditors"],
    "law firm": ["lawyers", "advocates", "legal advisors", "solicitors"],
}

KNOWN_CITY_LOCALITIES: dict[str, list[str]] = {
    "delhi": [
        "Rohini",
        "Connaught Place",
        "Dwarka",
        "South Extension",
        "Karol Bagh",
        "Lajpat Nagar",
        "Janakpuri",
        "Pitampura",
        "Vasant Kunj",
        "Saket",
        "Noida",
        "Gurugram",
    ],
    "delhi ncr": [
        "Rohini",
        "Connaught Place",
        "Dwarka",
        "South Extension",
        "Karol Bagh",
        "Lajpat Nagar",
        "Janakpuri",
        "Pitampura",
        "Vasant Kunj",
        "Saket",
        "Noida",
        "Gurugram",
    ],
    "new delhi": [
        "Rohini",
        "Connaught Place",
        "Dwarka",
        "South Extension",
        "Karol Bagh",
        "Lajpat Nagar",
        "Janakpuri",
        "Pitampura",
        "Vasant Kunj",
        "Saket",
    ],
    "bengaluru": [
        "Koramangala",
        "Indiranagar",
        "Whitefield",
        "HSR Layout",
        "Jayanagar",
        "Electronic City",
        "Marathahalli",
        "JP Nagar",
        "Bellandur",
    ],
    "bangalore": [
        "Koramangala",
        "Indiranagar",
        "Whitefield",
        "HSR Layout",
        "Jayanagar",
        "Electronic City",
        "Marathahalli",
        "JP Nagar",
        "Bellandur",
    ],
    "mumbai": [
        "Andheri",
        "Bandra",
        "Juhu",
        "Borivali",
        "Dadar",
        "Powai",
        "Thane",
        "Navi Mumbai",
        "Malad",
        "Colaba",
    ],
    "hyderabad": [
        "Banjara Hills",
        "Jubilee Hills",
        "Hitec City",
        "Gachibowli",
        "Madhapur",
        "Secunderabad",
        "Kukatpally",
        "Begumpet",
    ],
    "pune": [
        "Kothrud",
        "Viman Nagar",
        "Hinjewadi",
        "Baner",
        "Wakad",
        "Koregaon Park",
        "Hadapsar",
        "Aundh",
    ],
    "chennai": [
        "T. Nagar",
        "Adyar",
        "Velachery",
        "Anna Nagar",
        "Mylapore",
        "OMR",
        "Guindy",
        "Nungambakkam",
    ],
    "new york": ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island", "Midtown"],
    "london": ["City of London", "Westminster", "Camden", "Kensington", "Islington", "Shoreditch"],
}


@dataclass
class PlannedUnit:
    source_name: str
    unit_kind: str
    query_or_url: str
    locality: str | None = None
    execution_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanPlan:
    niche: str
    city: str
    country: str
    query_variants: list[str]
    locality_units: list[str]
    units: list[PlannedUnit]


def normalize_keyword(kw: str) -> str:
    return re.sub(r"\s+", " ", kw.strip().casefold())


def get_niche_aliases(niche: str) -> list[str]:
    norm = normalize_keyword(niche)
    aliases = [niche.strip()]
    if norm in COMMON_NICHE_ALIASES:
        for alias in COMMON_NICHE_ALIASES[norm]:
            if alias.casefold() not in [a.casefold() for a in aliases]:
                aliases.append(alias)
    else:
        # Check partial tokens
        for key, vals in COMMON_NICHE_ALIASES.items():
            if key in norm:
                for alias in vals:
                    if alias.casefold() not in [a.casefold() for a in aliases]:
                        aliases.append(alias)
    return aliases[:4]


def get_localities(city: str) -> list[str]:
    norm_city = normalize_keyword(city)
    # Check exact or partial match
    for known_city, localities in KNOWN_CITY_LOCALITIES.items():
        if known_city == norm_city or known_city in norm_city:
            return localities[:6]
    # Fallback cardinal localities for generic city
    clean_city = city.strip()
    return [
        clean_city,
        f"{clean_city} Central",
        f"{clean_city} North",
        f"{clean_city} South",
        f"{clean_city} East",
        f"{clean_city} West",
    ][:4]


def build_scan_plan(
    *,
    niche: str,
    city: str,
    country: str = "India",
    max_localities: int = 4,
    enabled_sources: list[str] | None = None,
) -> ScanPlan:
    """Plans multi-source discovery units with respectful partitioning."""
    clean_niche = niche.strip()
    clean_city = city.strip()
    clean_country = country.strip() or "India"

    niche_aliases = get_niche_aliases(clean_niche)
    localities = get_localities(clean_city)[:max_localities]

    sources = enabled_sources or ["searxng", "justdial", "google_maps"]

    query_variants: list[str] = []
    units: list[PlannedUnit] = []

    # 1. Broad City Queries per alias
    for alias in niche_aliases:
        variant = f"{alias} in {clean_city}"
        if variant not in query_variants:
            query_variants.append(variant)

    # 2. Locality Subqueries
    for loc in localities:
        variant = f"{clean_niche} in {loc}"
        if variant not in query_variants:
            query_variants.append(variant)

    # 3. Create Planned Units for each source
    # Limit number of queries per source to avoid excessive volume
    for source in sources:
        # Unit for main query
        units.append(
            PlannedUnit(
                source_name=source,
                unit_kind="city_primary",
                query_or_url=f"{clean_niche} in {clean_city}",
                locality=clean_city,
                execution_metadata={"alias": clean_niche, "scope": "city"},
            )
        )
        # Locality units
        for loc in localities:
            if loc.casefold() != clean_city.casefold():
                units.append(
                    PlannedUnit(
                        source_name=source,
                        unit_kind="locality_subquery",
                        query_or_url=f"{clean_niche} in {loc}",
                        locality=loc,
                        execution_metadata={"locality": loc, "scope": "suburb"},
                    )
                )

    return ScanPlan(
        niche=clean_niche,
        city=clean_city,
        country=clean_country,
        query_variants=query_variants,
        locality_units=localities,
        units=units,
    )
