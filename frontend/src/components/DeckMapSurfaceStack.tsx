import { NavigationArrowIcon } from "@phosphor-icons/react";

import type { MissionReport } from "../domain/types";
import type { MapVisualModeId } from "../map/mapConfig";
import { getMapSurface, getVisibleLayerIds, type MapSurfaceDefinition } from "../map/mapSurfaces";
import { DeckMapSurface } from "./DeckMapSurface";
import { MapModeSwitcher } from "./MapModeSwitcher";
import { MapSurfaceSwitcher } from "./MapSurfaceSwitcher";
import { PanelTitle } from "./PanelTitle";
import { Badge } from "./primitives/Badge";
import { Divider } from "./primitives/Divider";

interface DeckMapSurfaceStackProps {
  activeLayerIds: string[];
  activeMapSurfaceId: string;
  currentReport: MissionReport | null;
  mapMode: MapVisualModeId;
  onMapModeChange(mode: MapVisualModeId): void;
  onSurfaceChange(surfaceId: string): void;
  surfaces: MapSurfaceDefinition[];
}

const toneClass = {
  amber: "border-warning text-warning",
  blue: "border-fuel text-fuel",
  green: "border-success text-success",
  red: "border-destructive text-destructive",
};

export function DeckMapSurfaceStack({
  activeLayerIds,
  activeMapSurfaceId,
  currentReport,
  mapMode,
  onMapModeChange,
  onSurfaceChange,
  surfaces,
}: DeckMapSurfaceStackProps) {
  const activeSurface = getMapSurface(activeMapSurfaceId, surfaces);
  const activeReport =
    currentReport?.target.id === activeSurface.id ? currentReport : activeSurface.report;
  const activeLayers = activeReport.layers.filter((layer) => activeLayerIds.includes(layer.id));
  const hasHighFinding = activeReport.findings.some(
    (finding) => finding.severity === "high" || finding.severity === "critical"
  );

  return (
    <section className="absolute inset-0 isolate overflow-hidden bg-black">
      <div className="absolute inset-0">
        {surfaces.map((surface) => {
          const report = currentReport?.target.id === surface.id ? currentReport : surface.report;
          const surfaceLayerIds =
            surface.id === activeSurface.id ? activeLayerIds : getVisibleLayerIds(report);

          return (
            <DeckMapSurface
              active={surface.id === activeSurface.id}
              activeLayerIds={surfaceLayerIds}
              mapMode={mapMode}
              key={surface.id}
              report={report}
              surface={surface}
            />
          );
        })}
      </div>

      <div className="pointer-events-none absolute inset-0 z-20 bg-[radial-gradient(circle_at_center,transparent_0%,rgb(0_0_0_/_0.1)_48%,rgb(0_0_0_/_0.72)_100%)]" />
      <div className="pointer-events-none absolute inset-0 z-20 command-map-grid opacity-20" />

      <aside className="pointer-events-auto absolute left-0 top-ui-sm z-30 hidden w-72 flex-row gap-ui-sm border border-l-0 border-border bg-background/90 p-ui-sm shadow-long shadow-black/25 @2xl/main:flex">
        <Divider orientation="vertical" variant="dashed" className="h-auto w-3 self-stretch text-accent" />
        <div className="min-w-0 flex-1">
          <PanelTitle>Surface {activeSurface.order}</PanelTitle>
          <dl className="mt-ui-xs grid gap-2 text-[10px] uppercase">
            <Readout label="Target" value={activeSurface.target.name} />
            <Readout label="Radius" value={`${activeSurface.target.radiusKm} km`} />
            <Readout label="Layers" value={`${activeLayers.length}/${activeReport.layers.length} active`} />
            <Readout label="Findings" value={`${activeReport.findings.length} staged`} />
          </dl>
        </div>
      </aside>

      <div className="pointer-events-auto absolute right-ui-sm top-ui-sm z-30 hidden flex-col gap-ui-xs @2xl/main:flex">
        {activeLayers.map((layer) => (
          <Badge
            border="elbow"
            className={`justify-start bg-black/70 font-mono ${toneClass[layer.tone]}`}
            key={layer.id}
            size="sm"
            variant="secondary"
          >
            <span className="w-24 truncate">{layer.label}</span>
            <span className="text-white/60">{layer.count}</span>
          </Badge>
        ))}
      </div>

      <div className="absolute bottom-ui-xs left-ui-xs z-30 hidden flex-col gap-ui-xs @2xl/main:flex">
        <div className="pointer-events-none flex items-center gap-ui-xs bg-background/50 px-ui-xs py-ui-xxs font-mono text-[10px] uppercase text-muted-foreground">
          <NavigationArrowIcon size={13} className="text-terminal" weight="bold" />
          <span className="h-px w-16 bg-border" />
          <span>Interactive Deck.gl / Mapbox 3D</span>
        </div>
        <MapModeSwitcher activeMode={mapMode} onModeChange={onMapModeChange} />
        <MapSurfaceSwitcher
          activeMapSurfaceId={activeSurface.id}
          onSurfaceChange={onSurfaceChange}
          surfaces={surfaces}
        />
      </div>

      <div className="pointer-events-none absolute bottom-ui-xs right-ui-xs z-30 flex max-w-[calc(100%_-_16px)] flex-wrap justify-end gap-ui-xxs">
        <Badge variant="ghost" size="sm" className="bg-background/70 font-mono">
          {activeSurface.target.lat.toFixed(4)}
        </Badge>
        <Badge variant="ghost" size="sm" className="bg-background/70 font-mono">
          {activeSurface.target.lon.toFixed(4)}
        </Badge>
        <Badge variant={hasHighFinding ? "warning" : "success"} size="sm">
          {activeReport.findings.length || "No"} findings
        </Badge>
      </div>
    </section>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-ui-xs">
      <dt className="font-bold text-white">{label}</dt>
      <dd className="truncate text-muted-foreground">{value}</dd>
    </div>
  );
}
