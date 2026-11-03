"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { MapCanvas, type DrawMode } from "@/components/map/map-canvas";
import { Card, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import { useSession } from "@/components/providers/session-provider";
import type {
  AreaGeometry,
  DiscoveryJob,
  SearchArea,
  TileBatch,
  ViewportResponse,
} from "@/lib/api/types";

const RADIUS_OPTIONS = [0.5, 1, 2, 5, 10] as const;
const POLL_MS = 2000;

/** Map Intelligence: draw an area, run a real discovery job over it, and read the
 *  results back as pins that belong to whoever is looking at them.
 *
 *  Nothing here is illustrative. Pins come from the viewport query, the tile grid
 *  comes from job batches, and every count on the progress strip is a count the
 *  backend observed. When a source did not answer, the strip says so.
 */
export function MapIntelligenceView() {
  const { csrf, user } = useSession();
  const queryClient = useQueryClient();

  const [geometry, setGeometry] = useState<AreaGeometry | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [radiusKm, setRadiusKm] = useState<number>(2);
  const [category, setCategory] = useState("amenity=hospital");
  const [viewport, setViewport] = useState<[number, number, number, number] | null>(null);
  const [filters, setFilters] = useState({ websiteStatus: "", hasPhone: "" });
  const [selectedPinId, setSelectedPinId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [jobId, setJobId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onViewportChange = useCallback((bbox: [number, number, number, number]) => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => setViewport(bbox), 250);
  }, []);
  useEffect(
    () => () => {
      if (debounce.current) clearTimeout(debounce.current);
    },
    [],
  );

  const pins = useQuery({
    queryKey: ["viewport", viewport, filters, category, jobId],
    enabled: Boolean(viewport),
    queryFn: () => {
      if (!viewport) throw new Error("no viewport");
      const params = new URLSearchParams({ bbox: viewport.join(",") });
      // The query category is OSM syntax (amenity=hospital); what gets stored on a
      // business is the value (hospital). Filtering on the query string would
      // match nothing and read as an empty area.
      const storedCategory = category.split("=").pop()?.trim();
      if (storedCategory) params.set("category", storedCategory);
      if (filters.websiteStatus) params.set("website_status", filters.websiteStatus);
      if (filters.hasPhone) params.set("has_phone", filters.hasPhone);
      return api.get<ViewportResponse>(`/businesses/viewport?${params.toString()}`);
    },
  });

  const job = useQuery({
    queryKey: ["discovery-job", jobId],
    enabled: Boolean(jobId),
    queryFn: () => api.get<DiscoveryJob>(`/discovery/jobs/${jobId}`),
    refetchInterval: (query) => {
      const status = (query.state.data as DiscoveryJob | undefined)?.status;
      return status === "running" || status === "queued" ? POLL_MS : false;
    },
  });

  const batches = useQuery({
    queryKey: ["discovery-job-batches", jobId],
    enabled: Boolean(jobId),
    queryFn: () => api.get<TileBatch[]>(`/discovery/jobs/${jobId}/batches`),
    refetchInterval: job.data?.status === "running" ? POLL_MS : false,
  });

  const areas = useQuery({
    queryKey: ["search-areas"],
    queryFn: () => api.get<{ items: SearchArea[]; total: number }>("/discovery/areas"),
  });

  const totals = job.data?.report?.totals;
  const sources = job.data?.report?.sources ?? [];

  async function startDiscovery() {
    setError(null);
    setNotice(null);
    if (!geometry) {
      setError("Choose where to search first: pick a centre and radius, or draw an area.");
      return;
    }
    if (!category.trim()) {
      setError("A category is required, as an OSM tag such as amenity=hospital or shop=cafe.");
      return;
    }
    try {
      const created = await api.post<DiscoveryJob>(
        "/discovery/jobs",
        { category: category.trim(), geometry, sources: ["overpass"], max_results: 200 },
        csrf,
      );
      setJobId(created.id);
      setDrawMode("none");
      await queryClient.invalidateQueries({ queryKey: ["viewport"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function cancelJob() {
    if (!jobId) return;
    try {
      await api.post<DiscoveryJob>(`/discovery/jobs/${jobId}/cancel`, undefined, csrf);
      await job.refetch();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function saveArea() {
    if (!geometry) return;
    const name = window.prompt("Name this area", "Hisar search area");
    if (!name) return;
    try {
      await api.post<SearchArea>(
        "/discovery/areas",
        { name, geometry, categories: [category], module: "leads" },
        csrf,
      );
      await areas.refetch();
      setNotice(`Saved "${name}".`);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deleteArea(id: string) {
    try {
      await api.delete(`/discovery/areas/${id}`, csrf);
      await areas.refetch();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function shortlistSelected() {
    const ids = [...checked];
    if (ids.length === 0) return;
    let done = 0;
    for (const id of ids) {
      try {
        await api.post(`/businesses/${id}/shortlist`, undefined, csrf);
        done += 1;
      } catch {
        // One refusal must not pretend the rest never happened; the count below
        // is of records actually shortlisted.
      }
    }
    setNotice(`Shortlisted ${done} of ${ids.length}.`);
    await pins.refetch();
  }

  async function exportSelected() {
    const ids = [...checked];
    if (ids.length === 0) {
      setError("Select at least one record to export.");
      return;
    }
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"}/businesses/export/selected`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" },
          body: JSON.stringify({ ids }),
        },
      );
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "sparkxflow-selection.csv";
      link.click();
      URL.revokeObjectURL(url);
      setNotice(
        `Exported ${response.headers.get("X-Exported-Records") ?? ids.length} records` +
          (Number(response.headers.get("X-Export-Skipped") ?? 0) > 0
            ? `; ${response.headers.get("X-Export-Skipped")} were not yours to export.`
            : "."),
      );
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const pinListData = pins.data?.items;
  const pinList = useMemo(() => pinListData ?? [], [pinListData]);
  const selected = useMemo(
    () => pinList.find((pin) => pin.id === selectedPinId) ?? null,
    [pinList, selectedPinId],
  );

  if (!user) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header
        title="Map Explorer"
        subtitle={
          pins.data
            ? `${pins.data.total_in_viewport} records in view · ${pinList.length} drawn`
            : "Draw an area and discover the businesses inside it"
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-80">
          <Card>
            <CardTitle>Where</CardTitle>
            <div className="space-y-3 text-sm">
              <div className="flex gap-2">
                {(["none", "circle", "rectangle", "polygon"] as DrawMode[]).map((mode) => (
                  <button
                    className={buttonClass(drawMode === mode)}
                    key={mode}
                    onClick={() => setDrawMode(mode)}
                    type="button"
                  >
                    {mode === "none" ? "Pan" : mode}
                  </button>
                ))}
              </div>

              <label className="block">
                <span className="text-[var(--color-muted)]">Radius (km)</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {RADIUS_OPTIONS.map((option) => (
                    <button
                      className={buttonClass(radiusKm === option)}
                      key={option}
                      onClick={() => {
                        setRadiusKm(option);
                        setDrawMode("circle");
                      }}
                      type="button"
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </label>

              <p className="text-xs text-[var(--color-muted)]">
                {geometry
                  ? describeGeometry(geometry)
                  : "No area selected yet. Choose a radius, or draw a rectangle or polygon on the map."}
              </p>

              <div className="flex gap-2">
                <button className={buttonClass(false)} onClick={saveArea} type="button">
                  Save area
                </button>
                <button
                  className={buttonClass(false)}
                  onClick={() => {
                    setGeometry(null);
                    setDrawMode("none");
                  }}
                  type="button"
                >
                  Clear
                </button>
              </div>
            </div>
          </Card>

          <Card>
            <CardTitle>What</CardTitle>
            <div className="space-y-3 text-sm">
              <label className="block">
                <span className="text-[var(--color-muted)]">OSM category</span>
                <input
                  className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1"
                  onChange={(event) => setCategory(event.target.value)}
                  value={category}
                />
              </label>
              <p className="text-xs text-[var(--color-muted)]">
                key=value as OpenStreetMap stores it. A bare key finds anything carrying that tag.
              </p>

              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs">
                  <span className="text-[var(--color-muted)]">Website</span>
                  <select
                    className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1"
                    onChange={(event) =>
                      setFilters((current) => ({ ...current, websiteStatus: event.target.value }))
                    }
                    value={filters.websiteStatus}
                  >
                    <option value="">any</option>
                    <option value="available">has one</option>
                    <option value="missing">known missing</option>
                    <option value="unknown">not checked</option>
                  </select>
                </label>
                <label className="text-xs">
                  <span className="text-[var(--color-muted)]">Phone</span>
                  <select
                    className="mt-1 w-full rounded-md border border-border bg-[var(--color-background)] px-2 py-1"
                    onChange={(event) =>
                      setFilters((current) => ({ ...current, hasPhone: event.target.value }))
                    }
                    value={filters.hasPhone}
                  >
                    <option value="">any</option>
                    <option value="true">has one</option>
                    <option value="false">none reported</option>
                  </select>
                </label>
              </div>

              <button
                className="w-full rounded-md bg-[var(--color-primary)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                disabled={job.data?.status === "running" || !geometry}
                onClick={startDiscovery}
                type="button"
              >
                Start discovery
              </button>
            </div>
          </Card>

          <Card>
            <CardTitle>Saved areas</CardTitle>
            <div className="space-y-2 text-sm">
              {(areas.data?.items ?? []).length === 0 && (
                <p className="text-xs text-[var(--color-muted)]">Nothing saved yet.</p>
              )}
              {(areas.data?.items ?? []).map((area) => (
                <div className="flex items-center justify-between gap-2" key={area.id}>
                  <button
                    className="truncate text-left text-sm underline-offset-2 hover:underline"
                    onClick={() => {
                      setGeometry(geometryFor(area));
                      setDrawMode("none");
                    }}
                    type="button"
                  >
                    {area.name}
                    <span className="block text-xs text-[var(--color-muted)]">
                      {area.area_km2.toFixed(1)} km² ·{" "}
                      {area.last_run_at ? "has been run" : "never run"}
                    </span>
                  </button>
                  <button className="text-xs text-[var(--color-error)]" onClick={() => deleteArea(area.id)} type="button">
                    delete
                  </button>
                </div>
              ))}
            </div>
          </Card>
        </aside>

        <section className="flex min-h-[420px] min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1">
            <MapCanvas
              busy={pins.isFetching}
              drawMode={drawMode}
              geometry={geometry}
              onGeometryChange={(next) => {
                setGeometry(next);
                if (next?.shape_type === "circle") setRadiusKm(next.radius_km);
              }}
              onSelectPin={setSelectedPinId}
              onViewportChange={onViewportChange}
              pins={pinList}
              selectedPinId={selectedPinId}
              tiles={batches.data ?? []}
            />
          </div>

          {(job.data || notice || error) && (
            <div className="rounded-lg border border-border bg-[var(--color-surface)] p-3 text-sm">
              {error && <p className="text-[var(--color-error)]">{error}</p>}
              {notice && <p className="text-[var(--color-muted)]">{notice}</p>}
              {job.data && (
                <>
                  <p>
                    <strong>{job.data.status}</strong> · {totals?.units_done ?? 0}/
                    {totals?.units_total ?? 0} units · {totals?.discovered ?? 0} records returned ·{" "}
                    {totals?.stored_new ?? 0} new businesses · {totals?.rejected ?? 0} unusable ·{" "}
                    {job.data.report?.known_records_reseen ?? 0} already known
                  </p>
                  {sources.map((source) => (
                    <p className="mt-1 text-xs text-[var(--color-muted)]" key={source.slug}>
                      {source.slug}: {source.items_returned} records across {source.units} unit(s)
                      {source.failed
                        ? ` — ${source.units_failed} failed (${source.last_classification}: ${source.last_reason})`
                        : ""}
                      {source.units_truncated > 0
                        ? ` — ${source.units_truncated} capped by the provider`
                        : ""}
                    </p>
                  ))}
                  {job.data.error_details?.note ? (
                    <p className="mt-1 text-xs text-[var(--color-warning)]">
                      {String(job.data.error_details.note)}
                    </p>
                  ) : null}
                  {job.data.status === "running" && (
                    <button className={buttonClass(false)} onClick={cancelJob} type="button">
                      Cancel
                    </button>
                  )}
                </>
              )}
            </div>
          )}

          {selected && (
            <div className="rounded-lg border border-border bg-[var(--color-surface)] p-3 text-sm">
              <p className="font-medium">{selected.name}</p>
              <p className="text-xs text-[var(--color-muted)]">
                {selected.primary_category ?? "no category"} · website {selected.website_status} ·{" "}
                {selected.has_phone ? "phone reported" : "no phone reported"} ·{" "}
                {selected.rating != null
                  ? `${selected.rating}★ (${selected.review_count ?? 0} reviews)`
                  : "no rating reported"}
              </p>
            </div>
          )}
        </section>

        <aside className="flex w-full shrink-0 flex-col gap-3 lg:w-96">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Results
            </h2>
            <span className="text-xs text-[var(--color-muted)]">{checked.size} selected</span>
          </div>

          {pins.isError && (
            <p className="text-sm text-[var(--color-error)]">
              Results could not be loaded: {errorMessage(pins.error)}
            </p>
          )}
          {!pins.isFetching && pinList.length === 0 && !pins.isError && (
            <p className="text-sm text-[var(--color-muted)]">
              No stored records in this view. That means the sources you ran found nothing here —
              not that the area has no businesses.
            </p>
          )}
          {pins.data?.truncated && (
            <p className="text-xs text-[var(--color-warning)]">
              Showing {pins.data.returned} of {pins.data.total_in_viewport} matching records in this
              viewport. Zoom in to see the rest.
            </p>
          )}

          <ul className="max-h-[60vh] space-y-1 overflow-y-auto">
            {pinList.map((pin) => (
              <li key={pin.id}>
                <div
                  className={`flex items-start gap-2 rounded-md border p-2 text-sm ${
                    pin.id === selectedPinId ? "border-[var(--color-primary)]" : "border-border"
                  }`}
                >
                  <input
                    aria-label={`Select ${pin.name}`}
                    checked={checked.has(pin.id)}
                    onChange={(event) => {
                      setChecked((current) => {
                        const next = new Set(current);
                        if (event.target.checked) next.add(pin.id);
                        else next.delete(pin.id);
                        return next;
                      });
                    }}
                    type="checkbox"
                  />
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => setSelectedPinId(pin.id)}
                    type="button"
                  >
                    <span className="block truncate">{pin.name}</span>
                    <span className="block text-xs text-[var(--color-muted)]">
                      {pin.latitude.toFixed(5)}, {pin.longitude.toFixed(5)} · website{" "}
                      {pin.website_status}
                    </span>
                  </button>
                </div>
              </li>
            ))}
          </ul>

          <div className="flex gap-2">
            <button
              className={buttonClass(false)}
              disabled={checked.size === 0}
              onClick={shortlistSelected}
              type="button"
            >
              Shortlist selected
            </button>
            <button
              className={buttonClass(false)}
              disabled={checked.size === 0}
              onClick={exportSelected}
              type="button"
            >
              Export selected
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function buttonClass(active: boolean): string {
  return [
    "rounded-md border px-2 py-1 text-xs capitalize transition-colors",
    active
      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
      : "border-border text-[var(--color-muted)] hover:border-[var(--color-primary)]",
  ].join(" ");
}

function describeGeometry(geometry: AreaGeometry): string {
  if (geometry.shape_type === "circle") {
    return `Circle: ${geometry.radius_km} km around ${geometry.latitude.toFixed(4)}, ${geometry.longitude.toFixed(4)}.`;
  }
  if (geometry.shape_type === "rectangle") {
    const [west, south, east, north] = geometry.rectangle;
    return `Rectangle: ${((east - west) * 111).toFixed(1)} × ${((north - south) * 111).toFixed(1)} km.`;
  }
  if (geometry.shape_type === "polygon") {
    return `Polygon with ${geometry.polygon.length} vertices (needs at least 3 to run).`;
  }
  return "Administrative area bounding box.";
}

function geometryFor(area: SearchArea): AreaGeometry {
  if (
    area.shape_type === "circle" &&
    area.center_latitude != null &&
    area.center_longitude != null &&
    area.radius_m
  ) {
    return {
      shape_type: "circle",
      latitude: area.center_latitude,
      longitude: area.center_longitude,
      radius_km: area.radius_m / 1000,
    };
  }
  if (area.shape_type === "polygon" && area.polygon) {
    return { shape_type: "polygon", polygon: area.polygon };
  }
  return {
    shape_type: "administrative",
    bbox: [area.bbox_west, area.bbox_south, area.bbox_east, area.bbox_north],
  };
}

function errorMessage(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return "Something went wrong.";
}
