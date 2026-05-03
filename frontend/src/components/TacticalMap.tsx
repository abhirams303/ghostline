import type { MissionReport, MissionTarget } from "../domain/types";
import type { MapVisualModeId } from "../map/mapConfig";
import type { MapSurfaceDefinition } from "../map/mapSurfaces";
import { DeckMapSurfaceStack } from "./DeckMapSurfaceStack";

interface TacticalMapProps {
  activeLayerIds: string[];
  activeMapSurfaceId: string;
  mapMode: MapVisualModeId;
  onMapModeChange(mode: MapVisualModeId): void;
  onSurfaceChange(surfaceId: string): void;
  report: MissionReport | null;
  surfaces: MapSurfaceDefinition[];
  target: MissionTarget;
}

export function TacticalMap({
  activeLayerIds,
  activeMapSurfaceId,
  mapMode,
  onMapModeChange,
  onSurfaceChange,
  report,
  surfaces,
}: TacticalMapProps) {
  return (
    <DeckMapSurfaceStack
      activeLayerIds={activeLayerIds}
      activeMapSurfaceId={activeMapSurfaceId}
      currentReport={report}
      mapMode={mapMode}
      onMapModeChange={onMapModeChange}
      onSurfaceChange={onSurfaceChange}
      surfaces={surfaces}
    />
  );
}
