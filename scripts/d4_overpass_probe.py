"""D4 — measure what OpenStreetMap actually holds for Indian business categories.

The tile sizes, element caps and truncation rules in `architecture.md` 9.4 were
arithmetic until this script ran. Nothing in the product should state a coverage
figure this file did not observe.

Queries are built by the real `OverpassAdapter` wherever possible, so the numbers
describe the code that ships rather than a hand-written ideal. Counts come from
`out count;` (cheap for the server, and the honest way to learn an area's size
without pulling a whole city), and field richness from a bounded body sample.

Considerate by construction: one request in flight, a sleep between queries, an
identifying User-Agent, and an abort after repeated throttling — a probe that gets
the project blocked costs more than the numbers it collects.

    python scripts/d4_overpass_probe.py --out var/d4-overpass.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.modules.discovery.adapters.base import DiscoveryQuery, LocationSpec  # noqa: E402
from app.modules.discovery.adapters.overpass import (  # noqa: E402
    INTERPRETER_PATH,
    OverpassAdapter,
)

# An origin, not the interpreter URL: the adapter validates its base as an origin
# and appends the path itself, and the probe must do the same to measure the same
# request the product sends.
DEFAULT_ENDPOINT = "https://overpass-api.de"
USER_AGENT = "SparkXFlow-Nexus/0.1 (D4 coverage measurement; single-operator research tool)"

LOCATIONS: dict[str, tuple[float, float, str]] = {
    "hisar": (29.1499, 75.7211, "Hisar, HR"),
    "delhi": (28.6139, 77.2090, "New Delhi, DL"),
    "gurugram": (28.4595, 77.0266, "Gurugram, HR"),
}

# (location, OSM tag filter, radius km). Filters are the key=value form the adapter
# now emits; OSM stores a cafe as `amenity=cafe`, not as a tag named `cafe`.
COVERAGE_CASES: list[tuple[str, str, float]] = [
    ("hisar", "amenity=hospital", 5),
    ("hisar", "amenity=clinic", 5),
    ("hisar", "amenity=restaurant", 5),
    ("hisar", "tourism=hotel", 5),
    ("hisar", "amenity=school", 5),
    ("hisar", "leisure=fitness_centre", 5),
    ("hisar", "shop=grocery", 5),
    ("delhi", "amenity=hospital", 5),
    ("delhi", "amenity=restaurant", 5),
    ("gurugram", "amenity=restaurant", 5),
    ("gurugram", "shop=clothes", 5),
]

# Latency and element growth against radius, on one dense category.
TILE_RADII: list[float] = [1.0, 2.0, 5.0, 10.0, 20.0]

# What the adapter emitted before D4: the category as a tag key. Kept so the
# defect is documented with a number rather than an argument.
LEGACY_BASELINE = ("hisar", "hospital", 5.0)

SAMPLE_LIMIT = 200


def _adapter(endpoint: str, timeout: float) -> OverpassAdapter:
    return OverpassAdapter(endpoint, timeout_seconds=timeout, user_agent=USER_AGENT)


def _query(location: str, tags: str, radius_km: float, limit: int) -> DiscoveryQuery:
    lat, lon, _ = LOCATIONS[location]
    return DiscoveryQuery(
        category=tags,
        location=LocationSpec(center=(lat, lon), radius_km=radius_km),
        max_results=limit,
    )


async def _post(client: httpx.AsyncClient, endpoint: str, statement: str) -> tuple[int, dict[str, Any], int]:
    """POST a statement and time it.

    Statements come from `OverpassAdapter.build_query`, so the query text is the one
    that ships; the transport here is the probe's own client so the script can also
    ask for cheap `out count;` variants the adapter has no reason to expose.

    A 200 whose body is not JSON is treated as a failure, because that is exactly how
    the public interpreters answer when they are saturated: an HTML or XML error page
    with a success status. Counting that as "zero businesses found" would turn an
    outage into a coverage claim.
    """
    started = time.perf_counter()
    try:
        response = await client.post(endpoint, data={"data": statement})
    except httpx.HTTPError as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, round(
            (time.perf_counter() - started) * 1000
        )
    duration_ms = round((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        return response.status_code, {"error": response.text[:300]}, duration_ms
    try:
        payload = response.json()
    except ValueError:
        head = response.text[:180].replace("\n", " ")
        return (
            response.status_code,
            {"error": f"success status with non-JSON body: {head}"},
            duration_ms,
        )
    return response.status_code, payload, duration_ms


def _count_statement(base: str) -> str:
    """Swap the adapter's `out center N;` for `out count;` — same filter, no payload."""
    head, _, _ = base.rpartition("out center")
    return f"{head}out count;"


def _measure_elements(elements: list[dict[str, Any]]) -> dict[str, int]:
    tagged = [e for e in elements if isinstance(e.get("tags"), dict)]

    def has(keys: tuple[str, ...]) -> int:
        return sum(1 for e in tagged if any(e["tags"].get(key) for key in keys))

    return {
        "elements": len(elements),
        "types_node": sum(1 for e in elements if e.get("type") == "node"),
        "types_way": sum(1 for e in elements if e.get("type") == "way"),
        "types_relation": sum(1 for e in elements if e.get("type") == "relation"),
        "named": sum(1 for e in tagged if e["tags"].get("name")),
        "with_coordinates": sum(
            1
            for e in elements
            if e.get("lat") is not None or (e.get("center") or {}).get("lat") is not None
        ),
        "with_phone": has(("phone", "contact:phone")),
        "with_website": has(("website", "contact:website")),
        "with_email": has(("email", "contact:email")),
        "with_hours": has(("opening_hours",)),
        "with_address": has(("addr:street",)),
    }


async def run_case(
    client: httpx.AsyncClient,
    endpoint: str,
    adapter: OverpassAdapter,
    location: str,
    tags: str,
    radius_km: float,
    *,
    legacy: bool = False,
) -> dict[str, Any]:
    lat, lon, label = LOCATIONS[location]
    base = adapter.build_query(_query(location, tags, radius_km, SAMPLE_LIMIT))
    if legacy:
        # Reproduce the pre-D4 statement: nodes only, category as a tag key.
        base = (
            f'[out:json][timeout:25];(node["{tags}"](around:{int(radius_km * 1000)},{lat},{lon}));'
            f"out body {SAMPLE_LIMIT};"
        )

    record: dict[str, Any] = {
        "location": label,
        "tags": tags,
        "radius_km": radius_km,
        "geometry": f"circle({lat}, {lon}, {int(radius_km * 1000)}m)",
        "query_mode": "legacy_node_key" if legacy else "adapter",
        "sample_limit": SAMPLE_LIMIT,
    }

    status, payload, duration_ms = await _post(client, endpoint, _count_statement(base))
    record["count_duration_ms"] = duration_ms
    record["count_status"] = status
    if status != 200:
        record["error"] = payload.get("error", f"HTTP {status}")
        return record
    # `out count;` answers with one synthetic element carrying an `items` map:
    # nodes, ways, relations, areas and a total.
    items = next(
        (e.get("items") or {} for e in payload.get("elements") or [] if e.get("type") == "count"),
        {},
    )
    record["total_elements"] = items.get("total")
    record["count_nodes"] = items.get("nodes")
    record["count_ways"] = items.get("ways")
    record["count_relations"] = items.get("relations")
    record["count_areas"] = items.get("areas")

    status, body, duration_ms = await _post(client, endpoint, base)
    record["sample_duration_ms"] = duration_ms
    record["sample_status"] = status
    if status != 200:
        record["error"] = body.get("error", f"HTTP {status}")
        return record
    elements = body.get("elements")
    if not isinstance(elements, list):
        record["error"] = "success response without an elements array"
        return record
    record.update(_measure_elements(elements))
    record["truncated_at_limit"] = len(elements) >= SAMPLE_LIMIT
    return record


def _interpreter_url(origin: str) -> str:
    return f"{origin.rstrip('/')}{INTERPRETER_PATH}"


async def main_async(args: argparse.Namespace) -> int:
    interpreter = _interpreter_url(args.endpoint)
    cases: list[tuple[str, str, float, bool]] = [
        (loc, tags, max(0.5, radius * args.radius_scale), False)
        for loc, tags, radius in COVERAGE_CASES
    ]
    if not args.skip_legacy:
        loc, tags, radius = LEGACY_BASELINE
        cases.append((loc, tags, max(0.5, radius * args.radius_scale), True))
    if args.cases:
        cases = cases[: args.cases]

    tile_radii = [
        float(part) for part in args.tile_radii.split(",") if part.strip()
    ]
    adapter = _adapter(args.endpoint, args.timeout)
    results: list[dict[str, Any]] = []
    consecutive_throttles = 0

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=args.timeout
    ) as client:
        for index, (location, tags, radius_km, legacy) in enumerate(cases, start=1):
            print(
                f"[{index:2d}/{len(cases)}] {LOCATIONS[location][2]:<16} {tags:<26} "
                f"r={radius_km}km{'  (legacy)' if legacy else ''}",
                flush=True,
            )
            outcome = await run_case(
                client, interpreter, adapter, location, tags, radius_km, legacy=legacy
            )
            if "error" in outcome:
                print(f"    ERROR {outcome.get('count_status')} {str(outcome['error'])[:140]}")
                consecutive_throttles += 1
                if consecutive_throttles >= args.abort_after:
                    print("aborting: the endpoint is throttling us; retry another day")
                    break
                await asyncio.sleep(args.sleep * 4)
                continue
            consecutive_throttles = 0
            print(
                f"    total={outcome.get('total_elements')} sample={outcome['elements']} "
                f"named={outcome['named']} phone={outcome['with_phone']} "
                f"website={outcome['with_website']} coords={outcome['with_coordinates']} "
                f"({outcome['count_duration_ms']}ms + {outcome['sample_duration_ms']}ms)"
                f"{' TRUNCATED' if outcome['truncated_at_limit'] else ''}"
            )
            results.append(outcome)
            if index < len(cases):
                await asyncio.sleep(args.sleep)

        # Tile-size curve: counts only, so the server is not asked to ship a city.
        if not args.skip_tiles:
            for radius_km in tile_radii:
                lat, lon, label = LOCATIONS["delhi"]
                statement = _count_statement(
                    adapter.build_query(
                        _query("delhi", "amenity=hospital", radius_km, SAMPLE_LIMIT)
                    )
                )
                status, payload, duration_ms = await _post(client, interpreter, statement)
                entry = {
                    "location": label,
                    "tags": "amenity=hospital",
                    "radius_km": radius_km,
                    "area_km2": round(3.14159 * radius_km**2, 1),
                    "status": status,
                    "count_duration_ms": duration_ms,
                    "total_elements": next(
                        (
                            (e.get("items") or {}).get("total")
                            for e in payload.get("elements") or []
                            if e.get("type") == "count"
                        ),
                        None,
                    )
                    if status == 200
                    else None,
                    "error": payload.get("error") if status != 200 else None,
                }
                print(
                    f"[tile] r={radius_km:>5}km area={entry['area_km2']:>7}km² "
                    f"total={entry['total_elements']} in {duration_ms}ms",
                    flush=True,
                )
                results.append(entry)
                await asyncio.sleep(args.sleep)

    durations = [r["count_duration_ms"] for r in results if r.get("count_duration_ms")]
    summary = {
        "endpoint": args.endpoint,
        "sample_limit": SAMPLE_LIMIT,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_agent": USER_AGENT,
        "cases": len(results),
        "errors": sum(1 for r in results if "error" in r),
        "truncated": sum(1 for r in results if r.get("truncated_at_limit")),
        "count_duration_ms_p50": int(statistics.median(durations)) if durations else None,
        "count_duration_ms_max": max(durations) if durations else None,
        "results": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    await adapter.aclose()
    print(
        f"\nwrote {args.out}: {summary['cases']} cases, {summary['errors']} errors, "
        f"{summary['truncated']} truncated, count p50 {summary['count_duration_ms_p50']}ms / "
        f"max {summary['count_duration_ms_max']}ms"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--out", default="var/d4-overpass.json")
    parser.add_argument("--sleep", type=float, default=25.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--abort-after", type=int, default=2)
    parser.add_argument("--cases", type=int, default=0)
    parser.add_argument("--skip-legacy", action="store_true")
    parser.add_argument("--skip-tiles", action="store_true")
    parser.add_argument(
        "--radius-scale",
        type=float,
        default=1.0,
        help="shrink every radius; use small values when the public endpoint is saturated",
    )
    parser.add_argument("--tile-radii", default=",".join(str(r) for r in TILE_RADII))
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
