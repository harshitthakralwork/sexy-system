"use client";

import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Layers, MapPin, ZoomIn, ZoomOut } from "lucide-react";
import type { Business } from "@/lib/api/types";

export interface MapLeafCanvasProps {
  city: string;
  radiusKm: number;
  businesses: Business[];
  selectedId: string | null;
  onSelectBusiness: (business: Business) => void;
  className?: string;
}

// Known coordinates for major cities
const CITY_COORDINATES: Record<string, [number, number]> = {
  "new delhi": [28.6139, 77.209],
  delhi: [28.6139, 77.209],
  "delhi ncr": [28.6139, 77.209],
  mumbai: [19.076, 72.8777],
  bengaluru: [12.9716, 77.5946],
  bangalore: [12.9716, 77.5946],
  surat: [21.1702, 72.8311],
  jaipur: [26.9124, 75.7873],
  hyderabad: [17.385, 78.4867],
  pune: [18.5204, 73.8567],
  chennai: [13.0827, 80.2707],
  ahmedabad: [23.0225, 72.5714],
  chandigarh: [30.7333, 76.7794],
  indore: [22.7196, 75.8577],
  lucknow: [26.8467, 80.9462],
  kochi: [9.9312, 76.2673],
  goa: [15.2993, 74.124],
  noida: [28.5355, 77.391],
  gurugram: [28.4595, 77.0266],
  "new york": [40.7128, -74.006],
  london: [51.5074, -0.1278],
  dubai: [25.2048, 55.2708],
  singapore: [1.3521, 103.8198],
  toronto: [43.6532, -79.3832],
  "san francisco": [37.7749, -122.4194],
};

function getCityCoords(cityName: string): [number, number] {
  const normalized = cityName.trim().toLowerCase();
  for (const [key, coords] of Object.entries(CITY_COORDINATES)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return coords;
    }
  }
  return [28.6139, 77.209]; // Default to New Delhi if unknown
}

// Deterministic pseudo-random jitter within radius
function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function getBusinessCoords(b: Business, center: [number, number], radiusKm: number, idx: number): [number, number] {
  if (b.latitude && b.longitude && !isNaN(b.latitude) && !isNaN(b.longitude)) {
    return [b.latitude, b.longitude];
  }
  // Disperse realistically inside the circle radius
  const seed = hashString(b.id || b.name || `${idx}`);
  const angle = ((seed % 360) * Math.PI) / 180;
  const distFraction = Math.sqrt((seed % 1000) / 1000) * 0.85; // avoid outer edge
  const distKm = distFraction * radiusKm;

  const latOffset = (distKm / 111) * Math.cos(angle);
  const lngOffset = (distKm / (111 * Math.cos((center[0] * Math.PI) / 180))) * Math.sin(angle);

  return [center[0] + latOffset, center[1] + lngOffset];
}

// Marker color schemes matching Image 2
function getMarkerStyle(category: string | null, name: string) {
  const cat = (category || "").toLowerCase() + " " + name.toLowerCase();
  if (cat.includes("hospital") || cat.includes("speciality")) {
    return {
      bg: "bg-purple-600",
      border: "border-purple-300",
      glow: "shadow-[0_0_16px_rgba(168,85,247,0.85)]",
      fill: "#a855f7",
      iconSvg: `<path d="M12 6v12m-6-6h12" stroke="white" stroke-width="2.5" stroke-linecap="round"/>`,
    };
  }
  if (cat.includes("clinic") || cat.includes("care") || cat.includes("dental") || cat.includes("health")) {
    return {
      bg: "bg-emerald-500",
      border: "border-emerald-200",
      glow: "shadow-[0_0_16px_rgba(16,185,129,0.85)]",
      fill: "#10b981",
      iconSvg: `<path d="M7 12h10M12 7v10" stroke="white" stroke-width="2.5" stroke-linecap="round"/>`,
    };
  }
  // Centers, real estate, general services
  return {
    bg: "bg-amber-500",
    border: "border-amber-200",
    glow: "shadow-[0_0_16px_rgba(245,158,11,0.85)]",
    fill: "#f59e0b",
    iconSvg: `<circle cx="12" cy="12" r="4" fill="white"/>`,
  };
}

export default function MapLeafCanvas({
  city,
  radiusKm,
  businesses,
  selectedId,
  onSelectBusiness,
  className,
}: MapLeafCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const circleRef = useRef<L.Circle | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  const [mapType, setMapType] = useState<"satellite" | "dark">("satellite");
  const [zoomLevel, setZoomLevel] = useState<number>(12);

  // Initialize Map
  useEffect(() => {
    if (!containerRef.current) return;
    if (mapRef.current) return;

    const center = getCityCoords(city);

    const map = L.map(containerRef.current, {
      center,
      zoom: 12,
      zoomControl: false,
      attributionControl: true,
    });

    const satelliteLayer = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        maxZoom: 19,
        attribution: "Tiles &copy; Esri &mdash; Earthstar Geographics",
      }
    );

    satelliteLayer.addTo(map);
    tileLayerRef.current = satelliteLayer;

    // Search radius circle (matching purple zone from Image 2)
    const circle = L.circle(center, {
      radius: radiusKm * 1000,
      color: "#c084fc",
      weight: 2,
      fillColor: "#9333ea",
      fillOpacity: 0.18,
      dashArray: "6, 6",
    }).addTo(map);

    circleRef.current = circle;

    const markersGroup = L.layerGroup().addTo(map);
    markersLayerRef.current = markersGroup;

    map.on("zoomend", () => {
      setZoomLevel(map.getZoom());
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Handle map style toggle (Satellite vs Dark)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }

    if (mapType === "satellite") {
      const sat = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
          maxZoom: 19,
          attribution: "Tiles &copy; Esri",
        }
      ).addTo(map);
      tileLayerRef.current = sat;
    } else {
      const dark = L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        {
          maxZoom: 20,
          subdomains: "abcd",
          attribution: "&copy; CartoDB",
        }
      ).addTo(map);
      tileLayerRef.current = dark;
    }
  }, [mapType]);

  // Update center & radius when city or radius changes
  useEffect(() => {
    const map = mapRef.current;
    const circle = circleRef.current;
    if (!map || !circle) return;

    const center = getCityCoords(city);
    map.flyTo(center, 12, { duration: 1.2 });
    circle.setLatLng(center);
    circle.setRadius(radiusKm * 1000);
  }, [city, radiusKm]);

  // Render business markers
  useEffect(() => {
    const map = mapRef.current;
    const markersGroup = markersLayerRef.current;
    if (!map || !markersGroup) return;

    markersGroup.clearLayers();
    const center = getCityCoords(city);

    businesses.forEach((b, idx) => {
      const coords = getBusinessCoords(b, center, radiusKm, idx);
      const isSelected = b.id === selectedId;
      const style = getMarkerStyle(b.primary_category, b.name);

      const html = `
        <div class="relative flex items-center justify-center cursor-pointer group transition-transform duration-200 ${
          isSelected ? "scale-125 z-50" : "hover:scale-115"
        }">
          ${
            isSelected
              ? `<div class="absolute -inset-2 rounded-full bg-white/40 animate-ping"></div>`
              : ""
          }
          <div class="flex h-7 w-7 items-center justify-center rounded-full border-2 ${style.border} ${style.bg} ${style.glow}">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none">
              ${style.iconSvg}
            </svg>
          </div>
          <div class="absolute -bottom-1 h-1.5 w-1.5 rotate-45 ${style.bg}"></div>
        </div>
      `;

      const customIcon = L.divIcon({
        className: "custom-leaflet-marker",
        html,
        iconSize: [28, 28],
        iconAnchor: [14, 28],
        popupAnchor: [0, -28],
      });

      const marker = L.marker(coords, { icon: customIcon });

      const popupContent = `
        <div style="min-width: 180px; padding: 4px;">
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 2px;">${b.name}</div>
          <div style="font-size: 11px; opacity: 0.8; margin-bottom: 6px;">${b.primary_category || "Local Business"}</div>
          ${b.rating ? `<div style="font-size: 11px; color: #fbbf24; font-weight: 600;">★ ${b.rating.toFixed(1)} (${b.review_count || 0} reviews)</div>` : ""}
          ${b.address ? `<div style="font-size: 10px; opacity: 0.7; margin-top: 4px; line-height: 1.2;">${b.address}</div>` : ""}
          ${b.phone ? `<div style="font-size: 10px; color: #38bdf8; margin-top: 4px;">📞 ${b.phone}</div>` : ""}
        </div>
      `;

      marker.bindPopup(popupContent);
      marker.on("click", () => {
        onSelectBusiness(b);
      });

      markersGroup.addLayer(marker);

      if (isSelected) {
        marker.openPopup();
      }
    });
  }, [businesses, city, radiusKm, selectedId]);

  return (
    <div className={`relative h-full w-full overflow-hidden rounded-[24px] ${className || ""}`}>
      {/* Map DOM Element */}
      <div ref={containerRef} className="h-full w-full z-0" />

      {/* Top Left Radius Pill (from Image 2) */}
      <div className="absolute top-4 left-4 z-[400] flex items-center gap-2 rounded-full border border-purple-400/40 bg-purple-950/70 px-3.5 py-1.5 text-xs font-semibold text-purple-200 backdrop-blur-xl shadow-lg shadow-purple-950/50">
        <span className="h-2 w-2 rounded-full bg-purple-400 shadow-[0_0_8px_#c084fc] animate-pulse" />
        <span>{radiusKm} km radius</span>
      </div>

      {/* Top Right Legend (Hospitals / Clinics / Centers) */}
      <div className="absolute top-4 right-4 z-[400] flex flex-col gap-1.5 rounded-2xl border border-white/15 bg-black/60 p-3 text-[11px] font-medium text-white backdrop-blur-xl shadow-xl">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-purple-500 shadow-[0_0_6px_#a855f7]" />
          <span>Hospitals</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_6px_#10b981]" />
          <span>Clinics</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500 shadow-[0_0_6px_#f59e0b]" />
          <span>Medical Centers</span>
        </div>
      </div>

      {/* Bottom Left Area Selection Card (from Image 2) */}
      <div className="absolute bottom-4 left-4 z-[400] max-w-[280px] rounded-2xl border border-white/15 bg-black/65 p-3 text-xs text-white backdrop-blur-xl shadow-xl">
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-500/20 text-cyan-400">
            <MapPin size={12} />
          </div>
          <div>
            <div className="font-bold text-white">Area Selected: {radiusKm} km around {city}</div>
            <div className="text-[11px] text-white/60">{businesses.length} businesses found in this area</div>
          </div>
        </div>
      </div>

      {/* Bottom Right Controls (Satellite Toggle & Zoom) */}
      <div className="absolute bottom-4 right-4 z-[400] flex flex-col items-center gap-2">
        <button
          type="button"
          onClick={() => setMapType((prev) => (prev === "satellite" ? "dark" : "satellite"))}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/20 bg-black/70 text-white backdrop-blur-xl shadow-lg hover:bg-white/20 transition-all"
          title={`Switch to ${mapType === "satellite" ? "Dark Map" : "Satellite View"}`}
        >
          <Layers size={16} />
        </button>
        <div className="flex flex-col rounded-xl border border-white/20 bg-black/70 overflow-hidden backdrop-blur-xl shadow-lg">
          <button
            type="button"
            onClick={() => mapRef.current?.zoomIn()}
            className="flex h-8 w-8 items-center justify-center text-white hover:bg-white/20 transition-all border-b border-white/10"
            title="Zoom In"
          >
            <ZoomIn size={14} />
          </button>
          <button
            type="button"
            onClick={() => mapRef.current?.zoomOut()}
            className="flex h-8 w-8 items-center justify-center text-white hover:bg-white/20 transition-all"
            title="Zoom Out"
          >
            <ZoomOut size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

