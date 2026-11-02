"""Geographic input validation and area maths.

A polygon a user draws is untrusted input, exactly like a scraped page title: it
arrives from the browser, it decides how much work the system does, and it reaches a
shared public provider. So it is validated and measured here, before anything is
sent, and a request outside the ceilings is refused with a reason rather than
silently shrunk — a search that quietly covered half the area drawn would read to
the user as "no businesses here".

Nothing in this module touches the network or the database.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# Mean metres per degree of latitude on the WGS84 ellipsoid, and the spherical
# approximation used for areas. Areas here decide whether a request is *allowed*,
# not what is stored as a measurement, so ±0.5 % at city scale is well inside
# enough — and it keeps the maths auditable instead of pulling in a geodesy library.
KM_PER_DEGREE_LATITUDE = 110.574
KM_PER_DEGREE_LONGITUDE_EQUATOR = 111.320

MIN_POLYGON_VERTICES = 3
MAX_POLYGON_VERTICES = 200
# The Overpass adapter's own ceiling. Kept in one place so a radius accepted by the
# API cannot be a radius the provider will then refuse.
MAX_RADIUS_KM = 50.0
# Distances beyond this are not a search, they are a bulk download of a country.
MAX_AREA_KM2 = 2500.0


class GeometryError(ValueError):
    """A geometry the system will not act on, with the reason the user needs."""

    def __init__(self, message: str, *, field: str = "geometry") -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _validate_latitude(value: float, *, field: str = "latitude") -> float:
    if not math.isfinite(value) or not -90.0 <= value <= 90.0:
        raise GeometryError(f"{field} must be between -90 and 90.", field=field)
    return value


def _validate_longitude(value: float, *, field: str = "longitude") -> float:
    if not math.isfinite(value) or not -180.0 <= value <= 180.0:
        raise GeometryError(f"{field} must be between -180 and 180.", field=field)
    return value


def _km_between_latitudes(south: float, north: float) -> float:
    return abs(north - south) * KM_PER_DEGREE_LATITUDE


def _km_between_longitudes(west: float, east: float, at_latitude: float) -> float:
    # Meridian convergence: a degree of longitude is shorter away from the equator.
    return abs(east - west) * KM_PER_DEGREE_LONGITUDE_EQUATOR * math.cos(
        math.radians(at_latitude)
    )


@dataclass(frozen=True)
class BoundingBox:
    """An ordered geographic envelope. The unit every read is filtered by."""

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        _validate_latitude(self.south, field="bbox.south")
        _validate_latitude(self.north, field="bbox.north")
        _validate_longitude(self.west, field="bbox.west")
        _validate_longitude(self.east, field="bbox.east")
        if self.west > self.east or self.south > self.north:
            raise GeometryError(
                "Bounding box must be ordered (west <= east, south <= north).",
                field="bbox",
            )

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    @property
    def area_km2(self) -> float:
        mid_latitude = (self.south + self.north) / 2
        return (
            _km_between_longitudes(self.west, self.east, mid_latitude)
            * _km_between_latitudes(self.south, self.north)
        )

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.west, self.south, self.east, self.north


def _circle_bbox(latitude: float, longitude: float, radius_km: float) -> BoundingBox:
    delta_latitude = radius_km / KM_PER_DEGREE_LATITUDE
    # A radius that reaches a pole is not a usable circle for this product; the
    # cosine in the longitude conversion would divide by zero at exactly 90.
    if abs(latitude) + delta_latitude >= 90.0:
        raise GeometryError(
            "This circle reaches a pole. Move it away from the pole or reduce the radius.",
            field="latitude",
        )
    delta_longitude = radius_km / (
        KM_PER_DEGREE_LONGITUDE_EQUATOR * math.cos(math.radians(latitude))
    )
    return BoundingBox(
        west=max(longitude - delta_longitude, -180.0),
        south=latitude - delta_latitude,
        east=min(longitude + delta_longitude, 180.0),
        north=latitude + delta_latitude,
    )


def _polygon_area_km2(vertices: Sequence[tuple[float, float]]) -> float:
    """Shoelace on an equirectangular projection centred on the ring."""
    latitudes = [point[0] for point in vertices]
    mid_latitude = sum(latitudes) / len(latitudes)
    x_scale = KM_PER_DEGREE_LONGITUDE_EQUATOR * math.cos(math.radians(mid_latitude))
    scaled = [((lon * x_scale), (lat * KM_PER_DEGREE_LATITUDE)) for lat, lon in vertices]
    twice_area = sum(
        scaled[i][0] * scaled[(i + 1) % len(scaled)][1]
        - scaled[(i + 1) % len(scaled)][0] * scaled[i][1]
        for i in range(len(scaled))
    )
    return abs(twice_area) / 2


def _polygon_bbox(vertices: Sequence[tuple[float, float]]) -> BoundingBox:
    latitudes = [point[0] for point in vertices]
    longitudes = [point[1] for point in vertices]
    return BoundingBox(
        west=min(longitudes),
        south=min(latitudes),
        east=max(longitudes),
        north=max(latitudes),
    )


@dataclass(frozen=True)
class Circle:
    latitude: float
    longitude: float
    radius_km: float

    def __post_init__(self) -> None:
        _validate_latitude(self.latitude)
        _validate_longitude(self.longitude)
        if not math.isfinite(self.radius_km) or not 0 < self.radius_km <= MAX_RADIUS_KM:
            raise GeometryError(
                f"radius_km must be greater than 0 and at most {MAX_RADIUS_KM} km. "
                "Beyond that the request is a regional download, not a search: use a "
                "drawn area or the administrative level instead.",
                field="radius_km",
            )

    @property
    def bbox(self) -> BoundingBox:
        return _circle_bbox(self.latitude, self.longitude, self.radius_km)

    @property
    def area_km2(self) -> float:
        return math.pi * self.radius_km**2


@dataclass(frozen=True)
class Rectangle:
    west: float
    south: float
    east: float
    north: float

    @property
    def bbox(self) -> BoundingBox:
        return BoundingBox(west=self.west, south=self.south, east=self.east, north=self.north)

    @property
    def area_km2(self) -> float:
        return self.bbox.area_km2


@dataclass(frozen=True)
class Polygon:
    """A closed ring of (latitude, longitude) vertices. The first point is not
    repeated: closing the ring is the shape's job, not the caller's."""

    vertices: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.vertices) < MIN_POLYGON_VERTICES:
            raise GeometryError(
                f"A polygon needs at least {MIN_POLYGON_VERTICES} vertices.",
                field="polygon",
            )
        if len(self.vertices) > MAX_POLYGON_VERTICES:
            raise GeometryError(
                f"A polygon may have at most {MAX_POLYGON_VERTICES} vertices. "
                "That is far more outline than a search area needs; simplify the shape.",
                field="polygon",
            )
        for index, (latitude, longitude) in enumerate(self.vertices):
            _validate_latitude(latitude, field=f"polygon[{index}].latitude")
            _validate_longitude(longitude, field=f"polygon[{index}].longitude")

    @property
    def bbox(self) -> BoundingBox:
        return _polygon_bbox(self.vertices)

    @property
    def area_km2(self) -> float:
        return _polygon_area_km2(self.vertices)


@dataclass(frozen=True)
class Area:
    """One normalised geographic scope, whatever produced it."""

    shape_type: str
    bbox: BoundingBox
    area_km2: float
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int | None = None
    polygon: tuple[tuple[float, float], ...] | None = None

    @classmethod
    def from_circle(cls, circle: Circle) -> Area:
        return cls(
            shape_type="circle",
            bbox=circle.bbox,
            area_km2=circle.area_km2,
            latitude=circle.latitude,
            longitude=circle.longitude,
            radius_m=round(circle.radius_km * 1000),
        )

    @classmethod
    def from_rectangle(cls, rectangle: Rectangle) -> Area:
        return cls(shape_type="rectangle", bbox=rectangle.bbox, area_km2=rectangle.area_km2)

    @classmethod
    def from_polygon(cls, polygon: Polygon) -> Area:
        return cls(
            shape_type="polygon",
            bbox=polygon.bbox,
            area_km2=polygon.area_km2,
            polygon=polygon.vertices,
        )

    @classmethod
    def from_bounding_box(cls, bbox: BoundingBox) -> Area:
        """An administrative scope arrives resolved to a box by the geocoder."""
        return cls(shape_type="administrative", bbox=bbox, area_km2=bbox.area_km2)

    def within_ceiling(self, max_area_km2: float) -> bool:
        return self.area_km2 <= max_area_km2
