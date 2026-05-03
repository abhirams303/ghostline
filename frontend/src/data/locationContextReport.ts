import type { Finding, MapLayer, MissionReport, MissionScore, MissionTarget, Severity } from "../domain/types";
import type { GeocodedFeature, GeocodedLocation } from "../services/geocoding";

type BBox = [number, number, number, number];

export function createLocationContextReport(target: MissionTarget, location: GeocodedLocation): MissionReport {
  const primaryFeature: GeocodedFeature = {
    address: location.address,
    bbox: location.bbox,
    category: location.category,
    id: location.id,
    label: location.label,
    lat: location.lat,
    lon: location.lon,
    placeType: location.placeType,
    placeTypes: location.placeTypes,
    relevance: location.relevance,
    text: location.text,
  };
  const features = dedupeFeatures([primaryFeature, ...location.features]);
  const contextText = location.context.map((item) => `${item.type}:${item.text}`).join(" / ");
  const specificity = scoreSpecificity(location.placeType);
  const confidence = Math.round(clamp(location.relevance, 0, 1) * 100);
  const boundaryScore = location.bbox ? 82 : 48;
  const candidateScore = Math.max(38, 86 - Math.max(features.length - 1, 0) * 10);
  const score: MissionScore = {
    aggregate: Math.round((specificity + confidence + boundaryScore + candidateScore) / 4),
    movement: specificity,
    personnel: candidateScore,
    facility: boundaryScore,
    aerial: confidence,
  };

  return {
    runId: `mapbox-${target.id}-${Date.now().toString(36)}`,
    target,
    generatedAt: new Date().toISOString(),
    mode: "live",
    score,
    findings: buildFindings(target, location, features, contextText),
    layers: [...buildActualMapLayers(target, location, features), ...buildTacticalOverlayLayers(target)],
    narrative: [
      `Live Mapbox context loaded for ${location.label}.`,
      `Primary result is ${formatPlaceType(location.placeType)} at ${location.lat.toFixed(5)}, ${location.lon.toFixed(5)}.`,
      location.bbox
        ? "The geocoder returned a real boundary box, so the map can frame the returned place extent."
        : "The geocoder returned a point result, so the map is centered on the exact returned coordinate.",
      "No live Palantir ontology objects are configured in this workspace yet.",
    ].join(" "),
    mitigationPriorities: [
      "Use this result as the TargetArea seed before querying Palantir objects.",
      "Load live Observation, Asset, Unit, or Event objects from Foundry when OSDK config is available.",
      "Keep Mapbox result type and confidence visible so broad city matches are not mistaken for exact sites.",
      "Use the alternate geocoder candidates to catch ambiguous spoken locations.",
    ],
    aip: {
      state: "not_synced",
    },
  };
}

export function createTargetContextReport(target: MissionTarget): MissionReport {
  const score: MissionScore = {
    aggregate: 72,
    movement: 64,
    personnel: 58,
    facility: 76,
    aerial: 88,
  };

  return {
    runId: `target-${target.id}-${Date.now().toString(36)}`,
    target,
    generatedAt: new Date().toISOString(),
    mode: "live",
    score,
    findings: [
      {
        id: `${target.id}-configured-coordinate`,
        source: "mapbox",
        severity: "low",
        title: "Configured target coordinate loaded",
        summary: `${target.name} is using the configured target coordinate at ${target.lat.toFixed(5)}, ${target.lon.toFixed(5)} with a ${target.radiusKm} km operating radius.`,
        evidence: "Command deck target configuration",
        lat: target.lat,
        lon: target.lon,
        status: "new",
      },
      {
        id: `${target.id}-palantir-pending`,
        source: "palantir",
        severity: "medium",
        title: "Palantir ontology connection pending",
        summary: "The UI is ready to bind this target to live TargetArea, Observation, Asset, Unit, and Event objects once Foundry/OSDK configuration is provided.",
        evidence: "Local Palantir adapter boundary",
        status: "reviewing",
      },
    ],
    layers: [...buildConfiguredTargetLayers(target), ...buildTacticalOverlayLayers(target)],
    narrative:
      `${target.name} is displayed from configured coordinates and live Mapbox basemap data. ` +
      "The repeated synthetic ADS-B, OSINT, and revisit template has been removed from this surface. " +
      "Connect Palantir Foundry/OSDK to replace the pending ontology adapter with live operational objects.",
    mitigationPriorities: [
      "Bind this target to a Palantir TargetArea object.",
      "Query linked Observation and Event objects by geometry.",
      "Render actual unit, asset, and sensor tracks instead of local fixtures.",
      "Keep human review explicit before syncing operational decisions.",
    ],
    aip: {
      state: "not_synced",
    },
  };
}

export function estimateRadiusKm(location: GeocodedLocation): number {
  if (location.bbox) {
    const [west, south, east, north] = location.bbox;
    const midLat = (south + north) / 2;
    const lonKm = Math.abs(east - west) * 111.32 * Math.max(Math.cos((midLat * Math.PI) / 180), 0.2);
    const latKm = Math.abs(north - south) * 111.32;
    return clamp(Math.max(lonKm, latKm) / 2, 1.2, 80);
  }

  switch (location.placeType) {
    case "address":
    case "poi":
      return 1.6;
    case "neighborhood":
      return 4;
    case "locality":
    case "district":
      return 8;
    case "place":
      return 14;
    case "region":
      return 48;
    case "country":
      return 80;
    default:
      return 10;
  }
}

function buildFindings(
  target: MissionTarget,
  location: GeocodedLocation,
  features: GeocodedFeature[],
  contextText: string
): Finding[] {
  return [
    {
      id: `${target.id}-mapbox-primary`,
      source: "mapbox",
      severity: severityForConfidence(location.relevance),
      title: `Mapbox ${formatPlaceType(location.placeType)} result`,
      summary: `${location.label} was returned for "${location.query}" with ${Math.round((location.relevance || 0) * 100)}% geocoder relevance.`,
      evidence: location.id ?? "Mapbox geocoding result",
      lat: location.lat,
      lon: location.lon,
      status: "new",
    },
    {
      id: `${target.id}-mapbox-extent`,
      source: "mapbox",
      severity: location.bbox ? "low" : "medium",
      title: location.bbox ? "Returned place boundary available" : "Point-only geocoder result",
      summary: location.bbox
        ? `Mapbox returned a bounding box for ${location.label}; the result can be framed as an area.`
        : `Mapbox returned no boundary for ${location.label}; downstream Palantir lookup should use a buffered point geometry.`,
      evidence: location.bbox ? formatBBox(location.bbox) : "No bbox in Mapbox result",
      lat: location.lat,
      lon: location.lon,
      status: "reviewing",
    },
    {
      id: `${target.id}-mapbox-candidates`,
      source: "mapbox",
      severity: features.length > 2 ? "medium" : "low",
      title: `${features.length} geocoder candidate${features.length === 1 ? "" : "s"} returned`,
      summary:
        features.length > 1
          ? `Top alternatives include ${features.slice(1, 4).map((feature) => feature.label).join("; ")}.`
          : "No close alternate geocoder candidates were returned for this query.",
      evidence: "Mapbox forward geocoding candidates",
      status: "new",
    },
    {
      id: `${target.id}-mapbox-context`,
      source: "mapbox",
      severity: contextText ? "low" : "medium",
      title: contextText ? "Administrative context available" : "Administrative context sparse",
      summary: contextText || "The result did not include detailed administrative context.",
      evidence: "Mapbox context hierarchy",
      status: "new",
    },
  ];
}

function buildActualMapLayers(
  target: MissionTarget,
  location: GeocodedLocation,
  features: GeocodedFeature[]
): MapLayer[] {
  const layers: MapLayer[] = [
    {
      id: "layer-mapbox-geocoder",
      source: "mapbox",
      label: "Mapbox results",
      type: "marker",
      visible: true,
      count: features.length,
      tone: "green",
      data: features.map((feature, index) => ({
        position: [feature.lon, feature.lat],
        title: index === 0 ? `Primary: ${feature.text}` : `Candidate ${index + 1}: ${feature.text}`,
        detail: `${formatPlaceType(feature.placeType)} / relevance ${Math.round((feature.relevance || 0) * 100)}%`,
        radiusMeters: index === 0 ? Math.max(220, target.radiusKm * 110) : Math.max(140, target.radiusKm * 60),
      })),
    },
  ];

  const alternateFeatures = features.slice(1, 5);
  if (alternateFeatures.length > 0) {
    layers.push({
      id: "layer-candidate-links",
      source: "mapbox",
      label: "Candidate links",
      type: "path",
      visible: true,
      count: alternateFeatures.length,
      tone: "amber",
      data: alternateFeatures.map((feature, index) => ({
        path: [
          [location.lon, location.lat],
          [feature.lon, feature.lat],
        ],
        label: `Alternative ${index + 1}`,
        detail: `${feature.label} / ${Math.round(feature.relevance * 100)}% relevance`,
        minDistanceKm: distanceKm(location.lon, location.lat, feature.lon, feature.lat),
        sampleCount: 2,
      })),
    });
  }

  if (location.bbox) {
    layers.push({
      id: "layer-mapbox-bbox",
      source: "mapbox",
      label: "Result boundary",
      type: "polygon",
      visible: true,
      count: 1,
      tone: "blue",
      data: [
        {
          coordinates: bboxToCoordinates(location.bbox),
          title: `${location.text} boundary`,
          detail: formatBBox(location.bbox),
        },
      ],
    });
  }

  return layers;
}

function buildConfiguredTargetLayers(target: MissionTarget): MapLayer[] {
  return [
    {
      id: "layer-mapbox-target",
      source: "mapbox",
      label: "Target coordinate",
      type: "marker",
      visible: true,
      count: 1,
      tone: "green",
      data: [
        {
          position: [target.lon, target.lat],
          title: target.name,
          detail: `Configured target coordinate / ${target.theater}`,
          radiusMeters: Math.max(180, target.radiusKm * 90),
        },
      ],
    },
  ];
}

function buildTacticalOverlayLayers(target: MissionTarget): MapLayer[] {
  const corridorLength = Math.max(target.radiusKm * 1.05, 2);
  const corridorWidth = Math.max(target.radiusKm * 0.12, 0.32);
  const routeRadius = Math.max(target.radiusKm * 0.9, 2);
  const beaconRadius = Math.max(target.radiusKm * 0.26, 0.9);

  return [
    {
      id: "layer-control-corridors",
      source: "palantir",
      label: "Control corridors",
      type: "polygon",
      visible: true,
      count: 3,
      tone: "amber",
      data: [
        {
          coordinates: buildCorridorCoordinates(target, 28, corridorLength, corridorWidth),
          title: "North-east corridor",
          detail: "Angular corridor derived from target geometry",
        },
        {
          coordinates: buildCorridorCoordinates(target, 150, corridorLength * 0.88, corridorWidth),
          title: "South-east corridor",
          detail: "Angular corridor derived from target geometry",
        },
        {
          coordinates: buildCorridorCoordinates(target, 266, corridorLength * 0.95, corridorWidth),
          title: "West corridor",
          detail: "Angular corridor derived from target geometry",
        },
      ],
    },
    {
      id: "layer-approach-axes",
      source: "adsb",
      label: "Approach axes",
      type: "path",
      visible: true,
      count: 3,
      tone: "red",
      data: [24, 142, 258].map((bearing, index) => ({
        path: buildAxisPath(target, bearing, routeRadius),
        label: `Axis ${index + 1}`,
        minDistanceKm: corridorWidth,
        sampleCount: 3,
      })),
    },
    {
      id: "layer-insight-beacons",
      source: "palantir",
      label: "Insight beacons",
      type: "column",
      visible: true,
      count: 4,
      tone: "red",
      data: [
        {
          position: [target.lon, target.lat],
          title: "Primary geospatial fix",
          detail: "Small beacon for the active target coordinate",
          elevationMeters: 760,
          radiusMeters: 120,
          color: [216, 232, 255, 170],
        },
        {
          position: offsetPoint(target, beaconRadius, beaconRadius * 0.28),
          title: "East context node",
          detail: "Derived context checkpoint",
          elevationMeters: 520,
          radiusMeters: 95,
          color: [112, 177, 255, 150],
        },
        {
          position: offsetPoint(target, -beaconRadius * 0.62, beaconRadius * 0.78),
          title: "Northwest context node",
          detail: "Derived context checkpoint",
          elevationMeters: 460,
          radiusMeters: 95,
          color: [242, 196, 107, 145],
        },
        {
          position: offsetPoint(target, -beaconRadius * 0.16, -beaconRadius),
          title: "South context node",
          detail: "Derived context checkpoint",
          elevationMeters: 420,
          radiusMeters: 90,
          color: [236, 78, 78, 140],
        },
      ],
    },
  ];
}

function dedupeFeatures(features: GeocodedFeature[]): GeocodedFeature[] {
  const seen = new Set<string>();
  return features.filter((feature) => {
    const key = feature.id ?? `${feature.lon.toFixed(5)},${feature.lat.toFixed(5)},${feature.label}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function bboxToCoordinates([west, south, east, north]: BBox): Array<[number, number]> {
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
  ];
}

function buildCorridorCoordinates(
  target: MissionTarget,
  bearing: number,
  lengthKm: number,
  halfWidthKm: number
): Array<[number, number]> {
  const start = offsetBearing(target, bearing + 180, lengthKm * 0.16);
  const end = offsetBearing(target, bearing, lengthKm);
  const leftBearing = bearing - 90;
  const rightBearing = bearing + 90;

  return [
    offsetPointFromLngLat(target, start, leftBearing, halfWidthKm),
    offsetPointFromLngLat(target, end, leftBearing, halfWidthKm * 0.62),
    offsetPointFromLngLat(target, end, rightBearing, halfWidthKm * 0.62),
    offsetPointFromLngLat(target, start, rightBearing, halfWidthKm),
  ];
}

function buildAxisPath(target: MissionTarget, bearing: number, radiusKm: number) {
  return [
    offsetBearing(target, bearing + 180, radiusKm * 0.82),
    [target.lon, target.lat],
    offsetBearing(target, bearing, radiusKm),
  ];
}

function offsetBearing(target: MissionTarget, bearingDegrees: number, distanceKm: number): [number, number] {
  const radians = (bearingDegrees * Math.PI) / 180;
  return offsetPoint(target, Math.sin(radians) * distanceKm, Math.cos(radians) * distanceKm);
}

function offsetPointFromLngLat(
  target: MissionTarget,
  point: [number, number],
  bearingDegrees: number,
  distanceKm: number
): [number, number] {
  const radians = (bearingDegrees * Math.PI) / 180;
  const eastKm = Math.sin(radians) * distanceKm;
  const northKm = Math.cos(radians) * distanceKm;
  const lonScale = 111.32 * Math.max(Math.cos((target.lat * Math.PI) / 180), 0.2);

  return [point[0] + eastKm / lonScale, point[1] + northKm / 111.32];
}

function offsetPoint(target: MissionTarget, eastKm: number, northKm: number): [number, number] {
  const lonScale = 111.32 * Math.max(Math.cos((target.lat * Math.PI) / 180), 0.2);
  return [target.lon + eastKm / lonScale, target.lat + northKm / 111.32];
}

function distanceKm(lonA: number, latA: number, lonB: number, latB: number): number {
  const latKm = (latB - latA) * 111.32;
  const lonKm = (lonB - lonA) * 111.32 * Math.max(Math.cos((((latA + latB) / 2) * Math.PI) / 180), 0.2);
  return Math.sqrt(latKm * latKm + lonKm * lonKm);
}

function scoreSpecificity(placeType: string): number {
  switch (placeType) {
    case "address":
      return 96;
    case "poi":
      return 90;
    case "neighborhood":
      return 76;
    case "locality":
    case "district":
      return 68;
    case "place":
      return 58;
    case "region":
      return 42;
    case "country":
      return 28;
    default:
      return 52;
  }
}

function severityForConfidence(relevance: number): Severity {
  if (relevance >= 0.85) {
    return "low";
  }
  if (relevance >= 0.6) {
    return "medium";
  }
  return "high";
}

function formatPlaceType(value: string): string {
  return value.replace(/_/g, " ");
}

function formatBBox([west, south, east, north]: BBox): string {
  return `${south.toFixed(4)}, ${west.toFixed(4)} to ${north.toFixed(4)}, ${east.toFixed(4)}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
