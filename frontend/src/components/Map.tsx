"use client";

import { useMemo, useState } from "react";

import type { PickingInfo } from "@deck.gl/core";
import { DeckGL } from "@deck.gl/react";
import MapboxMap, { NavigationControl } from "react-map-gl/mapbox";

import { buildDeckLayers, getTooltipContent } from "@/lib/map/buildDeckLayers";
import {
  buildInitialViewState,
  DEFAULT_MAP_TARGET,
  MAPBOX_STYLE,
  MAPBOX_TOKEN
} from "@/lib/map/mapConfig";
import type { LayerViewModel } from "@/lib/layers";
import type { AnalyzeResponse, Finding } from "@/types/findings";

interface MapProps {
  report?: AnalyzeResponse | null;
  visibleLayerIds: string[];
  layers: LayerViewModel[];
}

export function Map({ report, visibleLayerIds, layers }: MapProps) {
  const fallbackTarget = DEFAULT_MAP_TARGET;
  const focalTarget = report?.target ?? fallbackTarget;
  const [hoverInfo, setHoverInfo] = useState<PickingInfo | null>(null);

  const deckLayers = useMemo(
    () => buildDeckLayers({ report, visibleLayerIds, fallbackTarget }),
    [fallbackTarget, report, visibleLayerIds]
  );

  const visibleFindings = (report?.findings ?? []).filter((finding) =>
    isFindingVisible(finding, visibleLayerIds)
  );
  const tooltip = hoverInfo ? getTooltipContent(hoverInfo) : null;

  return (
    <section className="overflow-hidden rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] shadow-panel">
      <div className="flex flex-col gap-4 border-b border-white/10 px-5 py-4 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Map Surface</p>
          <h2 className="mt-2 break-words font-display text-3xl text-[#f2eee4] [overflow-wrap:anywhere]">
            {report ? report.target.name : "Mapbox tactical surface"}
          </h2>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Real Mapbox basemap with `deck.gl` overlays translated from backend `layers` and findings.
          </p>
        </div>

        <div className="grid shrink-0 grid-cols-3 gap-2 text-right text-[10px] uppercase tracking-[0.24em] text-white/38">
          <StatChip label="Layers" value={`${layers.length || deckLayers.length}`} />
          <StatChip label="Visible" value={`${visibleLayerIds.length || deckLayers.length}`} />
          <StatChip label="Marks" value={`${visibleFindings.length || Math.max(deckLayers.length - 1, 0)}`} />
        </div>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="relative min-h-[520px] overflow-hidden rounded-[1.6rem] border border-white/10 bg-[#0b0f12]">
          {MAPBOX_TOKEN ? (
            <DeckGL
              key={`${focalTarget.lat}:${focalTarget.lon}:${focalTarget.radius_km}`}
              initialViewState={buildInitialViewState(focalTarget)}
              controller
              layers={deckLayers}
              onHover={setHoverInfo}
              getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
            >
              <MapboxMap
                reuseMaps
                mapboxAccessToken={MAPBOX_TOKEN}
                mapStyle={MAPBOX_STYLE}
                style={{ width: "100%", height: "100%" }}
                attributionControl={false}
              >
                <NavigationControl position="top-right" />
              </MapboxMap>
            </DeckGL>
          ) : (
            <div className="absolute inset-0 grid place-items-center bg-[radial-gradient(circle_at_50%_40%,rgba(143,246,210,0.12),transparent_28%),linear-gradient(180deg,#0b0f12_0%,#0d1215_100%)] p-6">
              <div className="max-w-md rounded-[1.4rem] border border-dashed border-white/10 bg-black/20 p-6 text-center">
                <p className="font-display text-3xl text-[#f2eee4]">Mapbox token required</p>
                <p className="mt-3 text-sm leading-6 text-white/55">
                  Set <span className="font-mono">NEXT_PUBLIC_MAPBOX_TOKEN</span> in
                  <span className="font-mono"> frontend/.env.local</span> to enable the real basemap.
                </p>
              </div>
            </div>
          )}

          <div className="pointer-events-none absolute left-4 top-4 rounded-full border border-white/10 bg-black/35 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.3em] text-[#f2eee4] backdrop-blur">
            {focalTarget.name}
          </div>

          {tooltip ? (
            <div
              className="pointer-events-none absolute z-20 hidden min-w-[220px] max-w-[260px] rounded-[1rem] border border-white/10 bg-[rgba(9,13,16,0.92)] text-[#f2eee4] shadow-2xl md:block"
              style={{ left: (hoverInfo?.x ?? 0) + 18, top: (hoverInfo?.y ?? 0) + 18 }}
              dangerouslySetInnerHTML={{ __html: tooltip.html ?? "" }}
            />
          ) : null}
        </div>

        <div className="space-y-3">
          <div className="rounded-[1.4rem] border border-white/10 bg-black/15 p-4">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#b8c1bd]">Target Fix</p>
            <div className="mt-4 space-y-3">
              <InfoRow label="Latitude" value={focalTarget.lat.toFixed(4)} />
              <InfoRow label="Longitude" value={focalTarget.lon.toFixed(4)} />
              <InfoRow label="Radius" value={`${focalTarget.radius_km} km`} />
              <InfoRow label="Mode" value={report?.mode.toUpperCase() ?? "STANDBY"} />
              <InfoRow label="Basemap" value="MAPBOX" />
            </div>
          </div>

          <div className="rounded-[1.4rem] border border-white/10 bg-black/15 p-4">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#b8c1bd]">Collector Marks</p>
            <div className="mt-4 space-y-2">
              {layers.length > 0 ? (
                layers.map((layer) => (
                  <div
                    key={layer.id}
                    className={`rounded-[1rem] border px-3 py-3 text-sm ${
                      visibleLayerIds.includes(layer.id)
                        ? "border-[#8ff6d2]/30 bg-[#8ff6d2]/8 text-[#eef8f3]"
                        : "border-white/10 bg-black/10 text-white/45"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-[11px] uppercase tracking-[0.24em]">
                        {layer.type}
                      </span>
                      <span className="text-xs">{layer.itemCount}</span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-white/55">
                  Synthetic overlays are active until a backend report is loaded.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function isFindingVisible(finding: Finding, visibleLayerIds: string[]) {
  if (visibleLayerIds.length === 0) {
    return true;
  }

  return visibleLayerIds.some((layerId) => layerId.toLowerCase().includes(finding.source));
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-white/45">{label}</span>
      <span className="min-w-0 break-all text-right font-mono text-[12px] uppercase tracking-[0.12em] text-[#f2eee4] md:tracking-[0.2em]">
        {value}
      </span>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-white/8 bg-black/10 px-3 py-2">
      <div className="text-lg text-[#f2eee4]">{value}</div>
      <div>{label}</div>
    </div>
  );
}
