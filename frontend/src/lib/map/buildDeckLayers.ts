import type { Layer, PickingInfo } from "@deck.gl/core";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { GeoJsonLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";

import type {
  AnalyzeResponse,
  Finding,
  LocationInput,
  MapLayerPayload,
} from "@/types/findings";

type TooltipRecord = {
  label: string;
  detail: string;
};

type MarkerDatum = TooltipRecord & {
  position: [number, number];
  radiusMeters: number;
  fillColor: [number, number, number, number];
  lineColor?: [number, number, number, number];
};

type PathDatum = TooltipRecord & {
  path: [number, number][];
  color: [number, number, number, number];
  width: number;
};

type PolygonFeature = GeoJSON.Feature<
  GeoJSON.Polygon,
  TooltipRecord & {
    lineColor: [number, number, number, number];
    fillColor: [number, number, number, number];
  }
>;

type HeatDatum = {
  position: [number, number];
  weight: number;
};

const SOURCE_COLORS = {
  strava: [143, 246, 210, 210] as [number, number, number, number],
  adsb: [242, 196, 107, 225] as [number, number, number, number],
  satellite: [245, 139, 100, 225] as [number, number, number, number],
  exa: [231, 236, 232, 210] as [number, number, number, number],
  system: [147, 162, 168, 190] as [number, number, number, number],
};

export function buildDeckLayers(params: {
  report?: AnalyzeResponse | null;
  visibleLayerIds: string[];
  fallbackTarget: LocationInput;
}): Layer[] {
  const { report, visibleLayerIds, fallbackTarget } = params;
  const target = report?.target ?? fallbackTarget;
  const layers: Layer[] = [
    buildTargetRadiusLayer(target),
    buildTargetMarkerLayer(target),
  ];

  if (!report) {
    return [...layers, ...buildFallbackDemoLayers(target)];
  }

  for (const layer of report.layers) {
    if (!visibleLayerIds.includes(layer.id)) {
      continue;
    }

    const deckLayer = mapPayloadToDeckLayer(layer);
    if (deckLayer) {
      layers.push(deckLayer);
    }
  }

  const findingLayer = buildFindingMarkerLayer(
    report.findings,
    visibleLayerIds,
  );
  if (findingLayer) {
    layers.push(findingLayer);
  }

  return layers;
}

export function getTooltipContent(info: PickingInfo) {
  const record = extractTooltipRecord(info.object);
  if (!record) {
    return null;
  }

  return {
    html: `<div style="padding:8px 10px;max-width:240px">
      <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;opacity:0.72;margin-bottom:4px">Map Signal</div>
      <div style="font-size:13px;font-weight:600;margin-bottom:4px">${escapeHtml(record.label)}</div>
      <div style="font-size:12px;line-height:1.5;opacity:0.86">${escapeHtml(record.detail)}</div>
    </div>`,
  };
}

function mapPayloadToDeckLayer(layer: MapLayerPayload): Layer | null {
  switch (layer.type) {
    case "marker":
      return buildMarkerPayloadLayer(layer);
    case "path":
      return buildPathPayloadLayer(layer);
    case "footprint":
      return buildFootprintPayloadLayer(layer);
    case "heatmap":
      return buildHeatmapPayloadLayer(layer);
    default:
      return null;
  }
}

function buildTargetRadiusLayer(target: LocationInput) {
  const data: PolygonFeature[] = [
    {
      type: "Feature",
      properties: {
        label: `${target.name} radius`,
        detail: `${target.radius_km} km assessment ring`,
        lineColor: [242, 238, 228, 190],
        fillColor: [242, 238, 228, 18],
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          buildCircleCoordinates([target.lon, target.lat], target.radius_km),
        ],
      },
    },
  ];

  return new GeoJsonLayer<PolygonFeature>({
    id: "target-radius-ring",
    data,
    stroked: true,
    filled: true,
    lineWidthMinPixels: 2,
    getLineColor: [242, 238, 228, 190],
    getFillColor: [242, 238, 228, 18],
    getLineWidth: 2,
    pickable: true,
  });
}

function buildTargetMarkerLayer(target: LocationInput) {
  return new ScatterplotLayer<MarkerDatum>({
    id: "target-center-marker",
    data: [
      {
        position: [target.lon, target.lat],
        radiusMeters: 260,
        fillColor: [242, 238, 228, 255],
        lineColor: [10, 10, 10, 180],
        label: target.name,
        detail: "Target center",
      },
    ],
    getPosition: (d) => d.position,
    getRadius: (d) => d.radiusMeters,
    radiusMinPixels: 7,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor ?? [0, 0, 0, 0],
    lineWidthMinPixels: 2,
    stroked: true,
    pickable: true,
  });
}

function buildFallbackDemoLayers(target: LocationInput): Layer[] {
  return [
    new HeatmapLayer<HeatDatum>({
      id: "fallback-demo-heatmap",
      data: [
        { position: [target.lon - 0.03, target.lat + 0.01], weight: 0.4 },
        { position: [target.lon + 0.02, target.lat - 0.015], weight: 0.8 },
        { position: [target.lon + 0.04, target.lat + 0.02], weight: 0.6 },
      ],
      getPosition: (d) => d.position,
      getWeight: (d) => d.weight,
      radiusPixels: 60,
      opacity: 0.6,
    }),
    new PathLayer<PathDatum>({
      id: "fallback-demo-path",
      data: [
        {
          path: [
            [target.lon - 0.08, target.lat - 0.04],
            [target.lon - 0.02, target.lat - 0.01],
            [target.lon + 0.05, target.lat + 0.02],
          ],
          color: SOURCE_COLORS.adsb,
          width: 5,
          label: "Synthetic transit corridor",
          detail: "Demo path shown before a run",
        },
      ],
      getPath: (d) => d.path,
      getColor: (d) => d.color,
      getWidth: (d) => d.width,
      widthMinPixels: 3,
      pickable: true,
    }),
    new ScatterplotLayer<MarkerDatum>({
      id: "fallback-demo-markers",
      data: [
        {
          position: [target.lon - 0.05, target.lat + 0.03],
          radiusMeters: 420,
          fillColor: SOURCE_COLORS.strava,
          label: "Synthetic signal A",
          detail: "Demo-only geospatial marker",
        },
        {
          position: [target.lon + 0.06, target.lat - 0.025],
          radiusMeters: 420,
          fillColor: SOURCE_COLORS.satellite,
          label: "Synthetic signal B",
          detail: "Demo-only geospatial marker",
        },
      ],
      getPosition: (d) => d.position,
      getRadius: (d) => d.radiusMeters,
      radiusMinPixels: 5,
      getFillColor: (d) => d.fillColor,
      pickable: true,
    }),
  ];
}

function buildMarkerPayloadLayer(layer: MapLayerPayload) {
  const data = layer.data
    .map((item) => {
      const position = toLngLat(item.position);
      if (!position) {
        return null;
      }

      const altitude = asNumber(item.altitudeFt);
      const speed = asNumber(item.groundSpeedKts);

      const minDistance = asNumber(item.minDistanceKm);
      const sampleCount = asNumber(item.sampleCount);

      return {
        position,
        radiusMeters: 520,
        fillColor: SOURCE_COLORS.adsb,
        label: asString(item.flight) || asString(item.hex) || "Aircraft marker",
        detail: [
          altitude !== null ? `${Math.round(altitude)} ft` : null,
          speed !== null ? `${Math.round(speed)} kts` : null,
          minDistance !== null
            ? `${minDistance.toFixed(1)} km min range`
            : null,
          sampleCount !== null ? `${Math.round(sampleCount)} samples` : null,
        ]
          .filter(Boolean)
          .join(" - "),
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
    radiusMinPixels: 5,
    getFillColor: (d) => d.fillColor,
    getLineColor: [10, 10, 10, 190],
    lineWidthMinPixels: 1.5,
    stroked: true,
    pickable: true,
    autoHighlight: true,
  });
}

function buildPathPayloadLayer(layer: MapLayerPayload) {
  const data = layer.data
    .map((item, index) => {
      const path = Array.isArray(item.path)
        ? item.path
            .map((point) => toLngLat(point))
            .filter((point): point is [number, number] => point !== null)
        : [];

      if (path.length < 2) {
        return null;
      }

      const minDistance = asNumber(item.minDistanceKm);
      const sampleCount = asNumber(item.sampleCount);
      return {
        path,
        color: SOURCE_COLORS.adsb,
        width: 6,
        label:
          asString(item.flight) || asString(item.hex) || `Path ${index + 1}`,
        detail: [
          `${path.length} vertices`,
          sampleCount !== null ? `${Math.round(sampleCount)} samples` : null,
          minDistance !== null
            ? `${minDistance.toFixed(1)} km min range`
            : null,
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
    rounded: true,
    pickable: true,
    autoHighlight: true,
  });
}

function buildFootprintPayloadLayer(layer: MapLayerPayload) {
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
          label: `Footprint ${index + 1}`,
          detail: `${radiusKm.toFixed(1)} km radius`,
          lineColor: SOURCE_COLORS.satellite,
          fillColor: [245, 139, 100, 32],
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
    getLineColor: [245, 139, 100, 225],
    getFillColor: [245, 139, 100, 32],
    lineWidthMinPixels: 2,
    getLineWidth: 2,
    pickable: true,
    autoHighlight: true,
  });
}

function buildHeatmapPayloadLayer(layer: MapLayerPayload) {
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
    radiusPixels: 70,
    intensity: 1,
    threshold: 0.05,
    opacity: 0.75,
  });
}

function buildFindingMarkerLayer(
  findings: Finding[],
  visibleLayerIds: string[],
) {
  const data = findings
    .filter((finding) => finding.geo)
    .filter((finding) => isFindingVisible(finding.source, visibleLayerIds))
    .map((finding) => ({
      position: [finding.geo!.lon, finding.geo!.lat] as [number, number],
      radiusMeters: 320,
      fillColor: SOURCE_COLORS[finding.source],
      lineColor: [255, 255, 255, 190] as [number, number, number, number],
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
    radiusMinPixels: 4,
    getFillColor: (d) => d.fillColor,
    getLineColor: (d) => d.lineColor ?? [255, 255, 255, 120],
    lineWidthMinPixels: 2,
    stroked: true,
    pickable: true,
    autoHighlight: true,
  });
}

function buildCircleCoordinates(
  center: [number, number],
  radiusKm: number,
  steps = 48,
) {
  const [lon, lat] = center;
  const points: [number, number][] = [];
  const latRadius = radiusKm / 111.32;
  const lonRadius =
    radiusKm / (111.32 * Math.max(Math.cos((lat * Math.PI) / 180), 0.2));

  for (let step = 0; step <= steps; step += 1) {
    const angle = (step / steps) * Math.PI * 2;
    points.push([
      lon + Math.cos(angle) * lonRadius,
      lat + Math.sin(angle) * latRadius,
    ]);
  }

  return points;
}

function isFindingVisible(
  source: Finding["source"],
  visibleLayerIds: string[],
) {
  if (visibleLayerIds.length === 0) {
    return true;
  }

  return visibleLayerIds.some((layerId) =>
    layerId.toLowerCase().includes(source),
  );
}

function toLngLat(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) {
    return null;
  }

  const lon = asNumber(value[0]);
  const lat = asNumber(value[1]);
  if (lon === null || lat === null) {
    return null;
  }

  return [lon, lat];
}

function asNumber(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function extractTooltipRecord(object: unknown): TooltipRecord | null {
  if (!object || typeof object !== "object") {
    return null;
  }

  const candidate = object as Partial<TooltipRecord> & {
    properties?: Partial<TooltipRecord>;
  };

  if (typeof candidate.label === "string") {
    return {
      label: candidate.label,
      detail: candidate.detail ?? "",
    };
  }

  if (typeof candidate.properties?.label === "string") {
    return {
      label: candidate.properties.label,
      detail: candidate.properties.detail ?? "",
    };
  }

  return null;
}
