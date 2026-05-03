import type { Layer, PickingInfo } from "@deck.gl/core";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer, GeoJsonLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";

import type { CollectorSource, Finding, MapLayer, MissionReport, MissionTarget } from "../domain/types";
import type { MapVisualModeId } from "./mapConfig";

type LngLat = [number, number];

type TooltipRecord = {
  label: string;
  detail: string;
};

type MarkerDatum = TooltipRecord & {
  position: LngLat;
  radiusMeters: number;
  fillColor: Color;
  lineColor?: Color;
};

type PathDatum = TooltipRecord & {
  path: LngLat[];
  color: Color;
  width: number;
};

type HeatDatum = {
  position: LngLat;
  weight: number;
};

type SignalColumnDatum = TooltipRecord & {
  position: LngLat;
  elevation: number;
  fillColor: Color;
  lineColor: Color;
  radius?: number;
};

type PolygonFeature = {
  type: "Feature";
  properties: TooltipRecord & {
    lineColor: Color;
    fillColor: Color;
  };
  geometry: {
    type: "Polygon";
    coordinates: LngLat[][];
  };
};

type Color = [number, number, number, number];

const SOURCE_COLORS = {
  strava: [236, 78, 78, 210],
  adsb: [242, 196, 107, 230],
  satellite: [112, 177, 255, 220],
  exa: [112, 240, 185, 215],
  palantir: [216, 232, 255, 220],
  mapbox: [94, 234, 212, 225],
  system: [232, 238, 226, 200],
} satisfies Record<CollectorSource, Color>;

export function buildDeckLayers(params: {
  activeLayerIds: string[];
  report: MissionReport;
  target: MissionTarget;
  visualMode?: MapVisualModeId;
}): Layer[] {
  const { activeLayerIds, report, target, visualMode = "dark" } = params;
  const layers: Layer[] = [buildTargetRadiusLayer(target), buildTargetMarkerLayer(target)];

  for (const layer of report.layers) {
    if (!activeLayerIds.includes(layer.id)) {
      continue;
    }

    const deckLayer = mapPayloadToDeckLayer(layer);
    if (deckLayer) {
      layers.push(deckLayer);
    }
  }

  const findingLayer = buildFindingMarkerLayer(report.findings);
  if (findingLayer) {
    layers.push(findingLayer);
  }

  if (visualMode === "terrain" || visualMode === "urban3d") {
    layers.push(buildSignalColumnLayer(report.findings, target, visualMode));
  }

  return layers;
}

export function getTooltipContent(info: PickingInfo) {
  const record = extractTooltipRecord(info.object);
  if (!record) {
    return null;
  }

  return {
    html: `<div style="padding:8px 10px;max-width:250px">
      <div style="font-size:10px;letter-spacing:0.18em;text-transform:uppercase;opacity:0.7;margin-bottom:4px">Map Signal</div>
      <div style="font-size:13px;font-weight:700;margin-bottom:4px">${escapeHtml(record.label)}</div>
      <div style="font-size:12px;line-height:1.45;opacity:0.86">${escapeHtml(record.detail)}</div>
    </div>`,
  };
}

function mapPayloadToDeckLayer(layer: MapLayer): Layer | null {
  switch (layer.type) {
    case "marker":
      return buildMarkerPayloadLayer(layer);
    case "path":
      return buildPathPayloadLayer(layer);
    case "footprint":
      return buildFootprintPayloadLayer(layer);
    case "polygon":
      return buildPolygonPayloadLayer(layer);
    case "heatmap":
      return buildHeatmapPayloadLayer(layer);
    case "column":
      return buildColumnPayloadLayer(layer);
    default:
      return null;
  }
}

function buildTargetRadiusLayer(target: MissionTarget) {
  const data: PolygonFeature[] = [
    {
      type: "Feature",
      properties: {
        label: `${target.name} AOI frame`,
        detail: `${target.radiusKm} km angular area of interest`,
        lineColor: [232, 238, 226, 185],
        fillColor: [232, 238, 226, 10],
      },
      geometry: {
        type: "Polygon",
        coordinates: [buildDiamondCoordinates([target.lon, target.lat], target.radiusKm)],
      },
    },
  ];

  return new GeoJsonLayer<PolygonFeature>({
    id: `${target.id}-target-radius`,
    data,
    stroked: true,
    filled: true,
    getLineColor: [232, 238, 226, 185],
    getFillColor: [232, 238, 226, 10],
    getLineWidth: 2,
    lineWidthMinPixels: 2,
    pickable: true,
  });
}

function buildTargetMarkerLayer(target: MissionTarget) {
  return new ScatterplotLayer<MarkerDatum>({
    id: `${target.id}-target-center`,
    data: [
      {
        position: [target.lon, target.lat],
        radiusMeters: 300,
        fillColor: [232, 238, 226, 250],
        lineColor: [0, 0, 0, 220],
        label: target.name,
        detail: "Command map focus",
      },
    ],
    getPosition: (d) => d.position,
    getRadius: (d) => d.radiusMeters,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor ?? [0, 0, 0, 0],
    lineWidthMinPixels: 2,
    radiusMinPixels: 7,
    stroked: true,
    pickable: true,
  });
}

function buildMarkerPayloadLayer(layer: MapLayer) {
  const color = SOURCE_COLORS[layer.source];
  const data = layer.data
    .map<MarkerDatum | null>((item, index) => {
      const position = toLngLat(item.position);
      if (!position) {
        return null;
      }

      return {
        position,
        radiusMeters: asNumber(item.radiusMeters) ?? 520,
        fillColor: color,
        lineColor: [0, 0, 0, 210] as Color,
        label: asString(item.title) || asString(item.label) || `${layer.label} ${index + 1}`,
        detail: asString(item.detail) || `${layer.source.toUpperCase()} marker`,
      } satisfies MarkerDatum;
    })
    .filter((item): item is MarkerDatum => item !== null);

  if (data.length === 0) {
    return null;
  }

  return new ScatterplotLayer<MarkerDatum>({
    id: layer.id,
    data,
    getPosition: (d) => d.position,
    getRadius: (d) => d.radiusMeters,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor ?? [0, 0, 0, 0],
    lineWidthMinPixels: 1.5,
    radiusMinPixels: 5,
    stroked: true,
    pickable: true,
    autoHighlight: true,
  });
}

function buildPathPayloadLayer(layer: MapLayer) {
  const color = SOURCE_COLORS[layer.source];
  const data = layer.data
    .map<PathDatum | null>((item, index) => {
      const path = Array.isArray(item.path)
        ? item.path.map((point) => toLngLat(point)).filter((point): point is LngLat => point !== null)
        : [];

      if (path.length < 2) {
        return null;
      }

      const minDistance = asNumber(item.minDistanceKm);
      const sampleCount = asNumber(item.sampleCount);

      return {
        path,
        color,
        width: 6,
        label: asString(item.flight) || asString(item.label) || `${layer.label} ${index + 1}`,
        detail: [
          `${path.length} vertices`,
          sampleCount !== null ? `${Math.round(sampleCount)} samples` : null,
          minDistance !== null ? `${minDistance.toFixed(1)} km min range` : null,
        ]
          .filter(Boolean)
          .join(" - "),
      } satisfies PathDatum;
    })
    .filter((item): item is PathDatum => item !== null);

  if (data.length === 0) {
    return null;
  }

  return new PathLayer<PathDatum>({
    id: layer.id,
    data,
    getPath: (d) => d.path,
    getColor: (d) => d.color,
    getWidth: (d) => d.width,
    widthMinPixels: 3,
    jointRounded: true,
    capRounded: true,
    pickable: true,
    autoHighlight: true,
  });
}

function buildFootprintPayloadLayer(layer: MapLayer) {
  const color = SOURCE_COLORS[layer.source];
  const data = layer.data
    .map<PolygonFeature | null>((item, index) => {
      const center = toLngLat(item.center);
      const radiusKm = asNumber(item.radiusKm);
      if (!center || radiusKm === null) {
        return null;
      }

      return {
        type: "Feature",
        properties: {
          label: asString(item.title) || `${layer.label} ${index + 1}`,
          detail: `${radiusKm.toFixed(1)} km footprint`,
          lineColor: color,
          fillColor: [color[0], color[1], color[2], 34] as Color,
        },
        geometry: {
          type: "Polygon",
          coordinates: [buildCircleCoordinates(center, radiusKm)],
        },
      } satisfies PolygonFeature;
    })
    .filter((item): item is PolygonFeature => item !== null);

  if (data.length === 0) {
    return null;
  }

  return new GeoJsonLayer<PolygonFeature>({
    id: layer.id,
    data,
    stroked: true,
    filled: true,
    getLineColor: color,
    getFillColor: [color[0], color[1], color[2], 34],
    getLineWidth: 2,
    lineWidthMinPixels: 2,
    pickable: true,
    autoHighlight: true,
  });
}

function buildPolygonPayloadLayer(layer: MapLayer) {
  const color = SOURCE_COLORS[layer.source];
  const data = layer.data
    .map<PolygonFeature | null>((item, index) => {
      const coordinates = Array.isArray(item.coordinates)
        ? item.coordinates.map((point) => toLngLat(point)).filter((point): point is LngLat => point !== null)
        : [];
      if (coordinates.length < 3) {
        return null;
      }

      return {
        type: "Feature",
        properties: {
          label: asString(item.title) || `${layer.label} ${index + 1}`,
          detail: asString(item.detail) || `${coordinates.length} polygon vertices`,
          lineColor: color,
          fillColor: [color[0], color[1], color[2], 32] as Color,
        },
        geometry: {
          type: "Polygon",
          coordinates: [[...coordinates, coordinates[0]]],
        },
      } satisfies PolygonFeature;
    })
    .filter((item): item is PolygonFeature => item !== null);

  if (data.length === 0) {
    return null;
  }

  return new GeoJsonLayer<PolygonFeature>({
    id: layer.id,
    data,
    stroked: true,
    filled: true,
    getLineColor: color,
    getFillColor: [color[0], color[1], color[2], 32],
    getLineWidth: 2,
    lineWidthMinPixels: 2,
    pickable: true,
    autoHighlight: true,
  });
}

function buildHeatmapPayloadLayer(layer: MapLayer) {
  const data = layer.data
    .map((item) => {
      const position = toLngLat(item.position);
      if (!position) {
        return null;
      }

      return {
        position,
        weight: asNumber(item.weight) ?? 0.6,
      } satisfies HeatDatum;
    })
    .filter((item): item is HeatDatum => item !== null);

  if (data.length === 0) {
    return null;
  }

  return new HeatmapLayer<HeatDatum>({
    id: layer.id,
    data,
    getPosition: (d) => d.position,
    getWeight: (d) => d.weight,
    intensity: 1,
    radiusPixels: 72,
    threshold: 0.05,
    opacity: 0.72,
  });
}

function buildColumnPayloadLayer(layer: MapLayer) {
  const color = SOURCE_COLORS[layer.source];
  const data = layer.data
    .map<SignalColumnDatum | null>((item, index) => {
      const position = toLngLat(item.position);
      if (!position) {
        return null;
      }

      return {
        position,
        elevation: asNumber(item.elevationMeters) ?? 760,
        fillColor: parseColor(item.color) ?? ([color[0], color[1], color[2], 155] as Color),
        lineColor: [255, 255, 255, 170] as Color,
        radius: asNumber(item.radiusMeters) ?? 140,
        label: asString(item.title) || asString(item.label) || `${layer.label} ${index + 1}`,
        detail: asString(item.detail) || `${layer.source.toUpperCase()} 3D volume`,
      } satisfies SignalColumnDatum;
    })
    .filter((item): item is SignalColumnDatum => item !== null);

  if (data.length === 0) {
    return null;
  }

  return new ColumnLayer<SignalColumnDatum>({
    id: layer.id,
    data,
    autoHighlight: true,
    coverage: 0.56,
    diskResolution: 6,
    elevationScale: 1,
    extruded: true,
    getElevation: (d) => d.elevation,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor,
    getPosition: (d) => d.position,
    lineWidthMinPixels: 1,
    pickable: true,
    radius: Math.min(220, Math.max(...data.map((item) => item.radius ?? 140))),
    stroked: true,
    wireframe: true,
  });
}

function buildFindingMarkerLayer(findings: Finding[]) {
  const data = findings
    .filter((finding) => typeof finding.lat === "number" && typeof finding.lon === "number")
    .map((finding) => ({
      position: [finding.lon!, finding.lat!] as LngLat,
      radiusMeters: 340,
      fillColor: SOURCE_COLORS[finding.source],
      lineColor: [255, 255, 255, 190] as Color,
      label: finding.title,
      detail: `${finding.source.toUpperCase()} - ${finding.severity.toUpperCase()}`,
    }));

  if (data.length === 0) {
    return null;
  }

  return new ScatterplotLayer<MarkerDatum>({
    id: "finding-markers",
    data,
    getPosition: (d) => d.position,
    getRadius: (d) => d.radiusMeters,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor ?? [255, 255, 255, 120],
    lineWidthMinPixels: 2,
    radiusMinPixels: 4,
    stroked: true,
    pickable: true,
    autoHighlight: true,
  });
}

function buildSignalColumnLayer(findings: Finding[], target: MissionTarget, visualMode: MapVisualModeId) {
  const findingsWithLocation = findings.filter(
    (finding) => typeof finding.lat === "number" && typeof finding.lon === "number"
  );
  const data: SignalColumnDatum[] =
    findingsWithLocation.length > 0
      ? findingsWithLocation.map((finding) => {
          const severity = getSeverityWeight(finding.severity);
          const color = SOURCE_COLORS[finding.source];

          return {
            position: [finding.lon!, finding.lat!] as LngLat,
            elevation: 300 + severity * 180,
            fillColor: [color[0], color[1], color[2], visualMode === "urban3d" ? 150 : 105],
            lineColor: [255, 255, 255, 165],
            label: finding.title,
            detail: `${finding.source.toUpperCase()} - ${finding.severity.toUpperCase()} vertical signal`,
          };
        })
      : [
          {
            position: [target.lon, target.lat],
            elevation: 680,
            fillColor: [220, 253, 56, visualMode === "urban3d" ? 140 : 100],
            lineColor: [255, 255, 255, 165],
            label: target.name,
            detail: "Target focus signal column",
          },
        ];

  return new ColumnLayer<SignalColumnDatum>({
    id: `${target.id}-signal-columns-${visualMode}`,
    data,
    autoHighlight: true,
    coverage: visualMode === "urban3d" ? 0.54 : 0.48,
    diskResolution: 6,
    elevationScale: visualMode === "urban3d" ? 1 : 0.72,
    extruded: true,
    getElevation: (d) => d.elevation,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor,
    getPosition: (d) => d.position,
    lineWidthMinPixels: 1,
    pickable: true,
    radius: visualMode === "urban3d" ? 110 : 140,
    stroked: true,
    wireframe: true,
  });
}

function getSeverityWeight(severity: Finding["severity"]) {
  switch (severity) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    case "low":
    default:
      return 1;
  }
}

function buildCircleCoordinates(center: LngLat, radiusKm: number, steps = 56): LngLat[] {
  const [lon, lat] = center;
  const points: LngLat[] = [];
  const latRadius = radiusKm / 111.32;
  const lonRadius = radiusKm / (111.32 * Math.max(Math.cos((lat * Math.PI) / 180), 0.2));

  for (let step = 0; step <= steps; step += 1) {
    const angle = (step / steps) * Math.PI * 2;
    points.push([lon + Math.cos(angle) * lonRadius, lat + Math.sin(angle) * latRadius]);
  }

  return points;
}

function buildDiamondCoordinates(center: LngLat, radiusKm: number): LngLat[] {
  const [lon, lat] = center;
  const latRadius = radiusKm / 111.32;
  const lonRadius = radiusKm / (111.32 * Math.max(Math.cos((lat * Math.PI) / 180), 0.2));

  return [
    [lon, lat + latRadius],
    [lon + lonRadius, lat],
    [lon, lat - latRadius],
    [lon - lonRadius, lat],
    [lon, lat + latRadius],
  ];
}

function toLngLat(value: unknown): LngLat | null {
  if (!Array.isArray(value) || value.length < 2) {
    return null;
  }

  const lon = Number(value[0]);
  const lat = Number(value[1]);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
    return null;
  }

  return [lon, lat];
}

function asNumber(value: unknown): number | null {
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseColor(value: unknown): Color | null {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }

  const [red, green, blue, alpha = 160] = value.map(Number);
  if (![red, green, blue, alpha].every(Number.isFinite)) {
    return null;
  }

  return [red, green, blue, alpha];
}

function extractTooltipRecord(value: unknown): TooltipRecord | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  if ("label" in value && "detail" in value) {
    return value as TooltipRecord;
  }

  if ("properties" in value) {
    const properties = (value as { properties?: unknown }).properties;
    if (properties && typeof properties === "object" && "label" in properties && "detail" in properties) {
      return properties as TooltipRecord;
    }
  }

  return null;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#039;";
      default:
        return char;
    }
  });
}
