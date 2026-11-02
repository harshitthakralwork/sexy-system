"use client";

import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type { MapPin, TileBatch } from "@/lib/api/types";
import type { AreaGeometry } from "@/lib/api/types";

export type DrawMode = "none" | "circle" | "rectangle" | "polygon";

const CLUSTER_ZOOM_THRESHOLD = 13;
const CLUSTER_PIXEL_GRID = 48;
/** Leaflet paints into canvas/SVG, where a CSS variable is not resolved. These are the
 *  theme's own values, repeated here on purpose rather than read at runtime. */
const PRIMARY = "#8b5cf6";

/** Tile-server attribution. Leaflet requires it on every OSM-compatible layer,
 *  and the licence the data comes under is not ours to quietly drop. */
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const TILE_STATUS_COLOURS: Record<string, string> = {
  completed: "#22c55e",
  running: "#a855f7",
  queued: "#64748b",
  failed: "#ef4444",
};

interface MapCanvasProps {
  pins: MapPin[];
  selectedPinId: string | null;
  onSelectPin: (id: string | null) => void;
  geometry: AreaGeometry | null;
  drawMode: DrawMode;
  onGeometryChange: (geometry: AreaGeometry | null) => void;
  tiles: TileBatch[];
  onViewportChange: (bbox: [number, number, number, number]) => void;
  busy: boolean;
}

/** Marker clustering by screen position rather than by a library.
 *
 *  A cluster here is a rendering device, not stored data: it says "n pins within
 *  this cell at this zoom", and clicking it zooms in until they separate. Keeping
 *  it local means no extra dependency and no second source of truth about what
 *  the map is showing.
 */
function clusterPins(pins: MapPin[], map: L.Map): MapPin[][] {
  if (map.getZoom() >= CLUSTER_ZOOM_THRESHOLD) {
    return pins.map((pin) => [pin]);
  }
  const cells = new Map<string, MapPin[]>();
  for (const pin of pins) {
    const point = map.project([pin.latitude, pin.longitude], map.getZoom());
    const key = `${Math.floor(point.x / CLUSTER_PIXEL_GRID)}:${Math.floor(
      point.y / CLUSTER_PIXEL_GRID,
    )}`;
    const bucket = cells.get(key) ?? [];
    bucket.push(pin);
    cells.set(key, bucket);
  }
  return [...cells.values()];
}

export function MapCanvas({
  pins,
  selectedPinId,
  onSelectPin,
  geometry,
  drawMode,
  onGeometryChange,
  tiles,
  onViewportChange,
  busy,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const pinLayer = useRef<L.LayerGroup | null>(null);
  const shapeLayer = useRef<L.LayerGroup | null>(null);
  const tileLayer = useRef<L.LayerGroup | null>(null);
  const draft = useRef<{ start: L.LatLng; rect?: L.Rectangle; poly?: L.Polygon } | null>(null);

  const emit = useMemo(
    () => (bbox: [number, number, number, number]) => onViewportChange(bbox),
    [onViewportChange],
  );

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [29.1499, 75.7211],
      zoom: 12,
      zoomControl: true,
      preferCanvas: true,
    });
    L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map);
    pinLayer.current = L.layerGroup().addTo(map);
    shapeLayer.current = L.layerGroup().addTo(map);
    tileLayer.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    const report = () => {
      const bounds = map.getBounds();
      emit([
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ]);
    };
    map.on("moveend", report);
    map.on("click", () => onSelectPin(null));
    report();
    return () => {
      map.off();
      map.remove();
      mapRef.current = null;
    };
  }, [emit, onSelectPin]);

  // Pins and clusters.
  useEffect(() => {
    const map = mapRef.current;
    const layer = pinLayer.current;
    if (!map || !layer) return;
    layer.clearLayers();

    for (const group of clusterPins(pins, map)) {
      if (group.length > 1) {
        const centre = L.latLngBounds(group.map((pin) => [pin.latitude, pin.longitude])).getCenter();
        const marker = L.circleMarker(centre, {
          radius: Math.min(20, 8 + Math.log2(group.length) * 2),
          color: PRIMARY,
          fillColor: PRIMARY,
          fillOpacity: 0.55,
          weight: 1,
        });
        marker.bindTooltip(`${group.length} records`, { direction: "center" });
        marker.on("click", (event) => {
          L.DomEvent.stopPropagation(event);
          map.fitBounds(L.latLngBounds(group.map((pin) => [pin.latitude, pin.longitude])), {
            padding: [30, 30],
          });
        });
        layer.addLayer(marker);
        continue;
      }
      const pin = group[0];
      const marker = L.circleMarker([pin.latitude, pin.longitude], {
        radius: pin.id === selectedPinId ? 9 : 6,
        color: pin.id === selectedPinId ? "#fbbf24" : PRIMARY,
        weight: pin.id === selectedPinId ? 3 : 1.5,
        fillColor: pin.website_status === "missing" ? "#f97316" : "#22c55e",
        fillOpacity: 0.85,
      });
      marker.bindTooltip(
        `<strong>${escapeHtml(pin.name)}</strong><br/>${
          pin.has_phone ? "phone reported" : "no phone reported"
        } · website ${pin.website_status}`,
        { direction: "top" },
      );
      marker.on("click", (event) => {
        L.DomEvent.stopPropagation(event);
        onSelectPin(pin.id);
      });
      layer.addLayer(marker);
    }
  }, [pins, selectedPinId, onSelectPin]);

  // The area being searched, and the tiles it was cut into.
  useEffect(() => {
    const map = mapRef.current;
    const shape = shapeLayer.current;
    const tileGroup = tileLayer.current;
    if (!map || !shape || !tileGroup) return;
    shape.clearLayers();
    tileGroup.clearLayers();

    if (geometry?.shape_type === "circle") {
      L.circle([geometry.latitude, geometry.longitude], {
        radius: geometry.radius_km * 1000,
        color: PRIMARY,
        weight: 2,
        fillOpacity: 0.08,
      }).addTo(shape);
    } else if (geometry?.shape_type === "rectangle") {
      const [west, south, east, north] = geometry.rectangle;
      L.rectangle([[south, west], [north, east]], {
        color: PRIMARY,
        weight: 2,
        fillOpacity: 0.08,
      }).addTo(shape);
    } else if (geometry?.shape_type === "polygon") {
      L.polygon(geometry.polygon, {
        color: PRIMARY,
        weight: 2,
        fillOpacity: 0.08,
      }).addTo(shape);
    } else if (geometry?.shape_type === "administrative") {
      const [west, south, east, north] = geometry.bbox;
      L.rectangle([[south, west], [north, east]], {
        color: PRIMARY,
        weight: 2,
        dashArray: "4 4",
        fillOpacity: 0.05,
      }).addTo(shape);
    }

    for (const tile of tiles) {
      if (!tile.bounds) continue;
      const { west, south, east, north } = tile.bounds;
      const rectangle = L.rectangle([[south, west], [north, east]], {
        color: TILE_STATUS_COLOURS[tile.status] ?? TILE_STATUS_COLOURS.queued,
        weight: 1,
        fillOpacity: 0.05,
      });
      rectangle.bindTooltip(
        `tile ${tile.batch_number} · ${tile.status}` +
          `${tile.truncated ? " · capped by the provider" : ""}` +
          ` · ${tile.records_processed} records` +
          `${tile.retry_count ? ` · retried ${tile.retry_count}×` : ""}`,
      );
      tileGroup.addLayer(rectangle);
    }
  }, [geometry, tiles]);

  // Drawing. The produced geometry is handed up and re-validated by the server
  // before it can start a job; the map never decides on its own what is allowed.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handlers: Array<[string, L.LeafletEventHandlerFn]> = [];

    const onDown: L.LeafletMouseEventHandlerFn = (event) => {
      if (drawMode === "circle") {
        onGeometryChange({
          shape_type: "circle",
          latitude: event.latlng.lat,
          longitude: event.latlng.lng,
          radius_km: 2,
        });
        return;
      }
      if (drawMode === "rectangle") {
        draft.current = { start: event.latlng };
      }
    };

    const onMove: L.LeafletMouseEventHandlerFn = (event) => {
      if (drawMode !== "rectangle" || !draft.current || !shapeLayer.current) return;
      const bounds = L.latLngBounds(draft.current.start, event.latlng);
      if (!draft.current.rect) {
        draft.current.rect = L.rectangle(bounds).addTo(shapeLayer.current);
      } else {
        draft.current.rect.setBounds(bounds);
      }
    };

    const onUp: L.LeafletMouseEventHandlerFn = (event) => {
      if (drawMode !== "rectangle" || !draft.current?.start) return;
      const bounds = L.latLngBounds(draft.current.start, event.latlng);
      const sw = bounds.getSouthWest();
      const ne = bounds.getNorthEast();
      draft.current = null;
      if (Math.abs(ne.lng - sw.lng) < 0.0005 || Math.abs(ne.lat - sw.lat) < 0.0005) return;
      onGeometryChange({
        shape_type: "rectangle",
        rectangle: [sw.lng, sw.lat, ne.lng, ne.lat],
      });
    };

    const onClick: L.LeafletMouseEventHandlerFn = (event) => {
      if (drawMode !== "polygon") return;
      const ring = currentPolygonRing(geometry);
      ring.push([event.latlng.lat, event.latlng.lng]);
      onGeometryChange({ shape_type: "polygon", polygon: ring });
    };

    if (drawMode !== "none") {
      handlers.push(["mousedown", mouse(onDown)], ["mousemove", mouse(onMove)], ["mouseup", mouse(onUp)]);
      if (drawMode === "polygon") handlers.push(["click", mouse(onClick)]);
      handlers.forEach(([name, handler]) => map.on(name, handler));
      map.dragging.disable();
    }
    return () => {
      handlers.forEach(([name, handler]) => map.off(name, handler));
      map.dragging.enable();
    };
  }, [drawMode, geometry, onGeometryChange]);

  return (
    <div
      aria-busy={busy}
      aria-label="Business discovery map"
      className="relative h-full w-full overflow-hidden rounded-lg border border-border"
      ref={containerRef}
      role="application"
    />
  );
}

/** Leaflet's `on` accepts the wide handler type; the drawing handlers all need
 *  the mouse event, so the narrowing lives here rather than at every call site. */
function mouse(handler: L.LeafletMouseEventHandlerFn): L.LeafletEventHandlerFn {
  return (event) => handler(event as L.LeafletMouseEvent);
}

function currentPolygonRing(geometry: AreaGeometry | null): [number, number][] {
  return geometry?.shape_type === "polygon" ? [...geometry.polygon] : [];
}

/** Leaflet tooltips accept HTML, and a business name is collected text. */
function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
