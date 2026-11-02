"""Geographic validation and tiling. Pure functions, no database, no network.

These are the guards that decide how much work a drawn shape is allowed to cause,
so the refusals matter as much as the acceptances: a user must never be told a
region was searched when only part of it was asked about.
"""

from __future__ import annotations

import math

import pytest

from app.modules.discovery.tiles import (
    MAX_TILE_GRID_DIMENSION,
    TilePlanError,
    plan_tiles,
    split_tile,
    subdivide_bbox,
)
from app.shared.geo import (
    MAX_POLYGON_VERTICES,
    MAX_RADIUS_KM,
    Area,
    BoundingBox,
    Circle,
    GeometryError,
    Polygon,
    Rectangle,
)

HISAR = (29.1499, 75.7211)


def _area_at_radius(radius_km: float) -> Area:
    return Area.from_circle(Circle(HISAR[0], HISAR[1], radius_km))


# --------------------------------------------------------------------- geometry


@pytest.mark.parametrize("radius_km", [0.1, 1.0, 25.0, MAX_RADIUS_KM])
def test_valid_circles_are_accepted(radius_km: float) -> None:
    circle = Circle(HISAR[0], HISAR[1], radius_km)
    assert circle.area_km2 == pytest.approx(math.pi * radius_km**2, rel=1e-6)
    assert circle.bbox.area_km2 > 0


@pytest.mark.parametrize("radius_km", [0.0, -1.0, MAX_RADIUS_KM + 0.1, 5000.0])
def test_radius_outside_the_ceiling_is_refused(radius_km: float) -> None:
    """The radius limit is the provider's, so the API must not accept beyond it."""
    with pytest.raises(GeometryError, match="radius_km"):
        Circle(HISAR[0], HISAR[1], radius_km)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (91.0, 75.7),
        (-95.0, 75.7),
        (29.1, 181.0),
        (29.1, -200.0),
        (float("nan"), 75.7),
        (29.1, float("inf")),
    ],
)
def test_impossible_coordinates_are_refused(latitude: float, longitude: float) -> None:
    with pytest.raises(GeometryError):
        Circle(latitude, longitude, 1.0)


def test_a_circle_reaching_a_pole_is_refused_not_wrapped() -> None:
    """A radius that crosses the pole would produce a bbox that wraps the globe."""
    with pytest.raises(GeometryError, match="pole"):
        Area.from_circle(Circle(89.9, 0.0, 50.0))


def test_bounding_box_must_be_ordered() -> None:
    with pytest.raises(GeometryError, match="ordered"):
        BoundingBox(west=77.7, south=28.7, east=77.5, north=28.5)


def test_rectangle_area_shrinks_with_latitude() -> None:
    """A degree of longitude is shorter away from the equator. Ignoring that would
    over-estimate every Indian search area by roughly 12%."""
    equator = Area.from_rectangle(Rectangle(0.0, 0.0, 1.0, 1.0))
    higher = Area.from_rectangle(Rectangle(75.0, 28.0, 76.0, 29.0))
    assert higher.area_km2 < equator.area_km2
    assert higher.area_km2 == pytest.approx(
        equator.area_km2 * math.cos(math.radians(28.5)), rel=1e-3
    )


def test_polygon_needs_three_vertices() -> None:
    with pytest.raises(GeometryError, match="at least 3 vertices"):
        Polygon(((29.1, 75.7), (29.2, 75.8)))


def test_polygon_vertex_limit_is_enforced() -> None:
    ring = tuple(
        (29.1 + 0.0001 * index, 75.7 + 0.0001 * index) for index in range(MAX_POLYGON_VERTICES + 1)
    )
    with pytest.raises(GeometryError, match="vertices"):
        Polygon(ring)


def test_polygon_rejects_a_bad_vertex() -> None:
    with pytest.raises(GeometryError, match="polygon\\[1\\]"):
        Polygon(((29.1, 75.7), (129.1, 75.7), (29.2, 75.8)))


def test_polygon_area_and_bbox_are_sane() -> None:
    square = Polygon(((29.0, 75.0), (29.0, 76.0), (30.0, 76.0), (30.0, 75.0)))
    assert square.bbox.as_tuple() == (75.0, 29.0, 76.0, 30.0)
    assert 9000 < square.area_km2 < 11000


def test_area_ceiling_comparison_is_inclusive() -> None:
    area = _area_at_radius(1.0)
    assert area.within_ceiling(area.area_km2)
    assert not area.within_ceiling(area.area_km2 - 0.01)


# ------------------------------------------------------------------------- tiles


def test_a_small_area_stays_one_unit_of_work() -> None:
    tiles = plan_tiles(_area_at_radius(1.0), target_area_km2=25.0, max_tiles=40)
    assert len(tiles) == 1


def test_a_large_area_splits_into_tiles_near_the_target_size() -> None:
    """The planner tiles the bounding box, so the invariant is the partition:
    N cells whose areas sum to the parent and none of them bigger than the parent."""
    area = _area_at_radius(10.0)
    tiles = plan_tiles(area, target_area_km2=25.0, max_tiles=40)
    assert len(tiles) > 1
    assert sum(tile.area_km2 for tile in tiles) == pytest.approx(area.bbox.area_km2, rel=1e-6)
    for tile in tiles:
        assert tile.area_km2 < area.bbox.area_km2 / 2


def test_tile_keys_are_deterministic_across_calls() -> None:
    """A re-run must recognise its own tiles, or it re-asks for ground already covered."""
    area = _area_at_radius(10.0)
    first = plan_tiles(area, target_area_km2=25.0, max_tiles=40)
    second = plan_tiles(area, target_area_km2=25.0, max_tiles=40)
    assert [tile.key for tile in first] == [tile.key for tile in second]

    moved = plan_tiles(_area_at_radius(10.0001), target_area_km2=25.0, max_tiles=40)
    assert [tile.key for tile in moved] != [tile.key for tile in first]


def test_tiles_partition_the_area_without_overlapping() -> None:
    """Shared edges are fine; overlapping interiors would double-count businesses."""
    area = _area_at_radius(10.0)
    tiles = plan_tiles(area, target_area_km2=25.0, max_tiles=40)
    covered = sum(tile.area_km2 for tile in tiles)
    assert covered == pytest.approx(area.bbox.area_km2, rel=1e-6)

    for a in tiles:
        for b in tiles:
            if a.index >= b.index:
                continue
            overlap_west = max(a.bbox.west, b.bbox.west)
            overlap_east = min(a.bbox.east, b.bbox.east)
            overlap_south = max(a.bbox.south, b.bbox.south)
            overlap_north = min(a.bbox.north, b.bbox.north)
            if overlap_east > overlap_west and overlap_north > overlap_south:
                raise AssertionError(f"tiles {a.index} and {b.index} overlap")


def test_tiling_covers_the_whole_bounding_box() -> None:
    area = _area_at_radius(10.0)
    tiles = plan_tiles(area, target_area_km2=25.0, max_tiles=40)
    assert min(tile.bbox.west for tile in tiles) == pytest.approx(area.bbox.west)
    assert max(tile.bbox.east for tile in tiles) == pytest.approx(area.bbox.east)
    assert min(tile.bbox.south for tile in tiles) == pytest.approx(area.bbox.south)
    assert max(tile.bbox.north for tile in tiles) == pytest.approx(area.bbox.north)


def test_a_region_needing_too_many_tiles_is_refused_with_the_number() -> None:
    """Refusing beats truncating: a partial search that reports itself as complete
    tells the user a city has no shops when it simply was not asked."""
    area = _area_at_radius(50.0)
    with pytest.raises(TilePlanError) as excinfo:
        plan_tiles(area, target_area_km2=25.0, max_tiles=40)
    details = excinfo.value.details
    assert details["tiles_required"] > details["max_tiles"]
    assert f"{details['tiles_required']} requests" in excinfo.value.message


def test_subdivision_quarters_a_tile_inside_its_parent() -> None:
    parent = plan_tiles(_area_at_radius(10.0), target_area_km2=25.0, max_tiles=40)[0]
    children = split_tile(parent)
    assert len(children) == 4
    assert sum(child.area_km2 for child in children) == pytest.approx(parent.area_km2, rel=1e-6)
    for child in children:
        assert child.bbox.west >= parent.bbox.west - 1e-9
        assert child.bbox.east <= parent.bbox.east + 1e-9
        assert child.key != parent.key


def test_a_single_subdivision_cannot_be_absurdly_fine() -> None:
    with pytest.raises(TilePlanError):
        subdivide_bbox(_area_at_radius(10.0).bbox, MAX_TILE_GRID_DIMENSION + 1, 1)
