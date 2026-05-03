import { useMemo } from "react";

import { DeckGL } from "@deck.gl/react";
import type { FogSpecification, LightSpecification } from "mapbox-gl";
import type { LayerProps } from "react-map-gl/mapbox";
import MapboxMap, { Layer, NavigationControl, Source } from "react-map-gl/mapbox";

import type { MissionReport } from "../domain/types";
import { buildDeckLayers, getTooltipContent } from "../map/buildDeckLayers";
import {
  getMapboxStyle,
  MAPBOX_TOKEN,
  type MapVisualModeId,
  uses3dBuildings,
  usesTerrain,
} from "../map/mapConfig";
import type { MapSurfaceDefinition } from "../map/mapSurfaces";
import { cn } from "../utils/tailwind";

interface DeckMapSurfaceProps {
  active: boolean;
  activeLayerIds: string[];
  mapMode: MapVisualModeId;
  report: MissionReport;
  surface: MapSurfaceDefinition;
}

export function DeckMapSurface({ active, activeLayerIds, mapMode, report, surface }: DeckMapSurfaceProps) {
  const deckLayers = useMemo(
    () => buildDeckLayers({ report, activeLayerIds, target: surface.target, visualMode: mapMode }),
    [activeLayerIds, mapMode, report, surface.target]
  );
  const terrainEnabled = usesTerrain(mapMode);
  const buildingsEnabled = uses3dBuildings(mapMode);
  const terrainSourceId = `${surface.id}-mapbox-dem`;

  return (
    <div
      aria-hidden={!active}
      className={cn(
        "absolute inset-0 overflow-hidden bg-black transition-opacity duration-150",
        active ? "z-10 opacity-100" : "pointer-events-none z-0 opacity-0"
      )}
      data-map-surface={surface.id}
    >
      {!MAPBOX_TOKEN ? (
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_42%,rgb(220_253_56_/_0.12),transparent_28%),linear-gradient(180deg,#050806_0%,#000_100%)]" />
      ) : null}

      <DeckGL
        controller={active}
        getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
        getTooltip={getTooltipContent}
        initialViewState={surface.viewState}
        layers={deckLayers}
        style={{ height: "100%", width: "100%" }}
      >
        {MAPBOX_TOKEN ? (
          <MapboxMap
            attributionControl={false}
            fog={mapMode === "urban3d" ? URBAN_FOG : TERRAIN_FOG}
            light={mapMode === "urban3d" ? URBAN_LIGHT : undefined}
            mapStyle={getMapboxStyle(mapMode)}
            mapboxAccessToken={MAPBOX_TOKEN}
            maxPitch={85}
            projection={mapMode === "satellite" ? "globe" : "mercator"}
            reuseMaps
            style={{ height: "100%", width: "100%" }}
            terrain={terrainEnabled ? { source: terrainSourceId, exaggeration: mapMode === "urban3d" ? 1.15 : 1.65 } : undefined}
          >
            {terrainEnabled ? (
              <Source
                id={terrainSourceId}
                maxzoom={14}
                tileSize={512}
                type="raster-dem"
                url="mapbox://mapbox.mapbox-terrain-dem-v1"
              >
                <Layer {...getHillshadeLayer(surface.id)} />
              </Source>
            ) : null}
            {buildingsEnabled ? <Layer {...getBuildingLayer(surface.id)} /> : null}
            {active ? <NavigationControl position="top-right" /> : null}
          </MapboxMap>
        ) : null}
      </DeckGL>

      {!MAPBOX_TOKEN ? (
        <div className="pointer-events-none absolute left-ui-sm top-ui-sm border border-warning/40 bg-background/85 px-ui-xs py-ui-xxs font-mono text-[10px] uppercase text-warning">
          NEXT_PUBLIC_MAPBOX_TOKEN missing - overlay fallback
        </div>
      ) : null}
    </div>
  );
}

const TERRAIN_FOG: FogSpecification = {
  color: "rgb(8, 14, 16)",
  "high-color": "rgb(30, 62, 76)",
  "horizon-blend": 0.08,
  range: [0.8, 8],
  "space-color": "rgb(0, 0, 0)",
};

const URBAN_FOG: FogSpecification = {
  color: "rgb(4, 9, 11)",
  "high-color": "rgb(26, 75, 82)",
  "horizon-blend": 0.06,
  range: [0.4, 7],
  "space-color": "rgb(0, 0, 0)",
};

const URBAN_LIGHT: LightSpecification = {
  anchor: "viewport",
  color: "#d9fff4",
  intensity: 0.48,
  position: [1.15, 210, 30],
};

function getHillshadeLayer(surfaceId: string): LayerProps {
  return {
    id: `${surfaceId}-terrain-hillshade`,
    type: "hillshade",
    paint: {
      "hillshade-accent-color": "#5eead4",
      "hillshade-exaggeration": 0.38,
      "hillshade-highlight-color": "#a7f3d0",
      "hillshade-shadow-color": "#020617",
    },
  };
}

function getBuildingLayer(surfaceId: string): LayerProps {
  return {
    id: `${surfaceId}-3d-buildings`,
    type: "fill-extrusion",
    source: "composite",
    "source-layer": "building",
    minzoom: 13,
    filter: ["==", ["get", "extrude"], "true"],
    paint: {
      "fill-extrusion-base": ["coalesce", ["get", "min_height"], 0],
      "fill-extrusion-color": [
        "interpolate",
        ["linear"],
        ["coalesce", ["get", "height"], 0],
        0,
        "#101820",
        90,
        "#164e63",
        180,
        "#0f766e",
        320,
        "#facc15",
      ],
      "fill-extrusion-height": ["coalesce", ["get", "height"], 0],
      "fill-extrusion-opacity": 0.68,
    },
  };
}
