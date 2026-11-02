"""Deterministic geographic tiling.

An area larger than one provider request can honestly cover is split into a grid of
tiles, and each tile becomes one unit of work with its own state. Three properties
matter here and they are all load-bearing:

* **Deterministic.** The same area and the same target size always produce the same
  tiles with the same keys, so a re-run can recognise work already done instead of
  asking a shared public provider for the same ground twice.
* **Non-overlapping.** Tiles partition the bounding box. Neighbours share an edge and
  nothing more, so a business on a boundary is found once, not four times.
* **Bounded.** Tile count is capped. A region that would exceed the cap is refused with
  the number it would have produced, because the alternative — quietly searching part
  of an area and reporting it as the whole — is the failure mode this feature exists to
  avoid.

The ceilings are provisional until D4's live measurements are reviewed; they are
configuration, not constants buried in the algorithm.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from app.shared.geo import Area, BoundingBox

MAX_TILE_GRID_DIMENSION = 64


class TilePlanError(ValueError):
    """A region that cannot be tiled inside the limits, with the reason."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class Tile:
    key: str
    index: int
    row: int
    column: int
    bbox: BoundingBox

    @property
    def area_km2(self) -> float:
        return self.bbox.area_km2

    def bounds_payload(self) -> dict[str, float]:
        west, south, east, north = self.bbox.as_tuple()
        return {"west": west, "south": south, "east": east, "north": north}


def _grid_dimensions(area: Area, target_area_km2: float) -> tuple[int, int]:
    """Rows and columns so each cell lands near `target_area_km2`."""
    if target_area_km2 <= 0:
        raise TilePlanError("target_area_km2 must be positive")
    bbox = area.bbox
    mid_latitude = bbox.centre[0]
    width_km = abs(bbox.east - bbox.west) * 111.32 * math.cos(math.radians(mid_latitude))
    height_km = abs(bbox.north - bbox.south) * 110.574
    side_km = math.sqrt(target_area_km2)
    columns = max(1, math.ceil(width_km / side_km))
    rows = max(1, math.ceil(height_km / side_km))
    return rows, columns


def _tile_key(
    area_signature: str, rows: int, columns: int, index: int, bbox: BoundingBox
) -> str:
    """Stable identity: derived from the geometry, never from a sequence number.

    A tile re-created tomorrow from the same saved area gets the same key, which is
    what lets the runner skip it instead of re-requesting it.
    """
    west, south, east, north = bbox.as_tuple()
    material = (
        f"{area_signature}|{rows}x{columns}|{index}"
        f"|{west:.7f}|{south:.7f}|{east:.7f}|{north:.7f}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def area_signature(area: Area) -> str:
    """A hash of the shape itself, so two areas that differ by a metre differ here."""
    west, south, east, north = area.bbox.as_tuple()
    material = (
        f"{area.shape_type}|{west:.7f}|{south:.7f}|{east:.7f}|{north:.7f}"
        f"|{area.radius_m}|{len(area.polygon or [])}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def subdivide_bbox(bbox: BoundingBox, rows: int, columns: int) -> list[BoundingBox]:
    """Split a box into rows x columns cells that share edges and overlap nowhere.

    Cell edges are computed from the parent's fractions rather than by stepping a
    delta, so the last column lands exactly on `east` instead of drifting short by
    accumulated rounding.
    """
    if rows < 1 or columns < 1:
        raise TilePlanError("rows and columns must be at least 1")
    if rows > MAX_TILE_GRID_DIMENSION or columns > MAX_TILE_GRID_DIMENSION:
        raise TilePlanError(
            f"A single subdivision of {rows}x{columns} is beyond what this planner will do."
        )
    cells: list[BoundingBox] = []
    for row in range(rows):
        south = bbox.south + (bbox.north - bbox.south) * row / rows
        north = bbox.south + (bbox.north - bbox.south) * (row + 1) / rows
        for column in range(columns):
            west = bbox.west + (bbox.east - bbox.west) * column / columns
            east = bbox.west + (bbox.east - bbox.west) * (column + 1) / columns
            cells.append(BoundingBox(west=west, south=south, east=east, north=north))
    return cells


def plan_tiles(
    area: Area, *, target_area_km2: float, max_tiles: int, plan_label: str = "area"
) -> list[Tile]:
    """Tile an area, or refuse with the numbers a user needs to shrink it."""
    rows, columns = _grid_dimensions(area, target_area_km2)
    produced = rows * columns
    if produced > max_tiles:
        raise TilePlanError(
            f"This {plan_label} would need {produced} requests "
            f"({rows} rows x {columns} columns), above the limit of {max_tiles}. "
            "Draw a smaller area, or work it a district at a time.",
            details={
                "tiles_required": produced,
                "max_tiles": max_tiles,
                "rows": rows,
                "columns": columns,
                "area_km2": round(area.area_km2, 2),
                "target_area_km2": target_area_km2,
            },
        )

    signature = area_signature(area)
    tiles: list[Tile] = []
    for index, cell in enumerate(subdivide_bbox(area.bbox, rows, columns)):
        tiles.append(
            Tile(
                key=_tile_key(signature, rows, columns, index, cell),
                index=index,
                row=index // columns,
                column=index % columns,
                bbox=cell,
            )
        )
    return tiles


def split_tile(tile: Tile) -> list[Tile]:
    """Quarter a tile when a provider answered the whole of it and was cut short.

    Only called on truncation, which is the one case where more requests are
    justified: the area is known to hold more records than the element cap allowed,
    so the count is unknown and the region has to be asked in smaller pieces.
    """
    cells = subdivide_bbox(tile.bbox, 2, 2)
    return [
        Tile(
            key=_tile_key(f"split:{tile.key}", 2, 2, index, cell),
            index=index,
            row=index // 2,
            column=index % 2,
            bbox=cell,
        )
        for index, cell in enumerate(cells)
    ]
