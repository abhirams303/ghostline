import type { AgentDescriptor, Finding, MapLayer, MissionReport, MissionTarget } from "../domain/types";

export const targets: MissionTarget[] = [
  {
    id: "fort-liberty",
    name: "Fort Liberty",
    lat: 35.139,
    lon: -78.997,
    radiusKm: 20,
    theater: "CONUS"
  },
  {
    id: "norfolk-naval",
    name: "Naval Station Norfolk",
    lat: 36.9466,
    lon: -76.3013,
    radiusKm: 18,
    theater: "Atlantic"
  },
  {
    id: "creech-afb",
    name: "Creech AFB",
    lat: 36.5872,
    lon: -115.6767,
    radiusKm: 25,
    theater: "Western Range"
  },
  {
    id: "jblm",
    name: "Joint Base Lewis-McChord",
    lat: 47.0876,
    lon: -122.5726,
    radiusKm: 22,
    theater: "Pacific Northwest"
  },
  {
    id: "naval-base-san-diego",
    name: "Naval Base San Diego",
    lat: 32.6839,
    lon: -117.1286,
    radiusKm: 18,
    theater: "Pacific"
  },
  {
    id: "shack15",
    name: "Shack15",
    lat: 37.7955,
    lon: -122.3937,
    radiusKm: 5,
    theater: "Civilian"
  }
];

export const defaultAgents: AgentDescriptor[] = [
  {
    id: "voice",
    name: "Voice Agent",
    role: "Pipecat operator interface",
    status: "listening",
    currentTask: "Awaiting command"
  },
  {
    id: "fusion",
    name: "Fusion Worker",
    role: "Background task agent",
    status: "idle",
    currentTask: "Collector fan-out"
  },
  {
    id: "aip",
    name: "AIP Sync Worker",
    role: "Palantir adapter",
    status: "idle",
    currentTask: "Ontology writeback"
  }
];

function offsetPoint(target: MissionTarget, eastKm: number, northKm: number): [number, number] {
  const lonScale = 111.32 * Math.max(Math.cos((target.lat * Math.PI) / 180), 0.2);
  return [target.lon + eastKm / lonScale, target.lat + northKm / 111.32];
}

function buildLayersForTarget(target: MissionTarget): MapLayer[] {
  const inboundTrack = [
    offsetPoint(target, -target.radiusKm * 0.82, -target.radiusKm * 0.38),
    offsetPoint(target, -target.radiusKm * 0.34, -target.radiusKm * 0.12),
    offsetPoint(target, target.radiusKm * 0.18, target.radiusKm * 0.14),
    offsetPoint(target, target.radiusKm * 0.62, target.radiusKm * 0.34),
  ];
  const crossTrack = [
    offsetPoint(target, -target.radiusKm * 0.18, target.radiusKm * 0.58),
    offsetPoint(target, target.radiusKm * 0.1, target.radiusKm * 0.18),
    offsetPoint(target, target.radiusKm * 0.48, -target.radiusKm * 0.2),
  ];
  const publicHits = [
    offsetPoint(target, -target.radiusKm * 0.42, target.radiusKm * 0.16),
    offsetPoint(target, target.radiusKm * 0.34, -target.radiusKm * 0.1),
    offsetPoint(target, target.radiusKm * 0.12, target.radiusKm * 0.44),
  ];
  const heatPoints = [
    offsetPoint(target, -target.radiusKm * 0.55, -target.radiusKm * 0.24),
    offsetPoint(target, -target.radiusKm * 0.28, -target.radiusKm * 0.34),
    offsetPoint(target, target.radiusKm * 0.08, -target.radiusKm * 0.18),
    offsetPoint(target, target.radiusKm * 0.36, target.radiusKm * 0.08),
    offsetPoint(target, target.radiusKm * 0.54, target.radiusKm * 0.26),
  ];

  return [
    {
      id: "layer-adsb",
      source: "adsb",
      label: "Aerial tracks",
      type: "path",
      visible: true,
      count: 2,
      tone: "amber",
      data: [
        {
          flight: "OBS-214",
          path: inboundTrack,
          minDistanceKm: target.radiusKm * 0.32,
          sampleCount: 18,
        },
        {
          flight: "CIV-762",
          path: crossTrack,
          minDistanceKm: target.radiusKm * 0.48,
          sampleCount: 11,
        },
      ],
    },
    {
      id: "layer-exa",
      source: "exa",
      label: "Public web hits",
      type: "marker",
      visible: true,
      count: publicHits.length,
      tone: "green",
      data: publicHits.map((position, index) => ({
        position,
        title: `Public-source hit ${index + 1}`,
        detail: `${target.name} open-source reference cluster`,
        radiusMeters: 560,
      })),
    },
    {
      id: "layer-satellite",
      source: "satellite",
      label: "Revisit windows",
      type: "footprint",
      visible: true,
      count: 2,
      tone: "blue",
      data: [
        {
          center: offsetPoint(target, -target.radiusKm * 0.08, target.radiusKm * 0.08),
          radiusKm: target.radiusKm * 0.74,
          title: "Daylight revisit footprint",
        },
        {
          center: offsetPoint(target, target.radiusKm * 0.24, -target.radiusKm * 0.12),
          radiusKm: target.radiusKm * 0.42,
          title: "Secondary collection window",
        },
      ],
    },
    {
      id: "layer-strava",
      source: "strava",
      label: "Movement heat",
      type: "heatmap",
      visible: false,
      count: heatPoints.length,
      tone: "red",
      data: heatPoints.map((position, index) => ({
        position,
        weight: 0.42 + index * 0.12,
      })),
    },
  ];
}

const findingsByTarget: Record<string, Finding[]> = {
  "fort-liberty": [
    {
      id: "fl-adsb-1",
      source: "adsb",
      severity: "high",
      title: "Predictable aerial observation pattern",
      summary: "Repeated public aircraft positions create a recurring observation window near the operating area.",
      evidence: "ADS-B Exchange snapshot",
      lat: 35.154,
      lon: -79.021,
      status: "new"
    },
    {
      id: "fl-exa-1",
      source: "exa",
      severity: "medium",
      title: "Public reporting mentions training tempo",
      summary: "Recent public web results reference exercises and schedule-adjacent language around the installation.",
      evidence: "Public web corpus",
      lat: 35.132,
      lon: -78.987,
      status: "new"
    },
    {
      id: "fl-sat-1",
      source: "satellite",
      severity: "medium",
      title: "Daylight revisit overlap",
      summary: "Mock revisit windows overlap high-activity daytime periods and should be reviewed against actual schedules.",
      evidence: "Synthetic revisit model",
      status: "reviewing"
    },
    {
      id: "fl-strava-1",
      source: "strava",
      severity: "high",
      title: "Movement heat near perimeter roads",
      summary: "Dummy movement heat indicates a repeatable public activity signature near route anchors.",
      evidence: "Mock heatmap tile summary",
      lat: 35.119,
      lon: -79.044,
      status: "new"
    }
  ],
  "norfolk-naval": [
    {
      id: "nn-adsb-1",
      source: "adsb",
      severity: "medium",
      title: "Dense public air traffic context",
      summary: "High ambient traffic makes correlation harder, but several low-altitude tracks require review.",
      evidence: "ADS-B Exchange snapshot",
      lat: 36.958,
      lon: -76.319,
      status: "new"
    },
    {
      id: "nn-exa-1",
      source: "exa",
      severity: "high",
      title: "Port-adjacent public activity cluster",
      summary: "Open reporting and public references cluster near logistics corridors.",
      evidence: "Public web corpus",
      status: "reviewing"
    },
    {
      id: "nn-sat-1",
      source: "satellite",
      severity: "medium",
      title: "Waterfront infrastructure revisit",
      summary: "Mock revisit estimates indicate repeated daylight collection opportunity over key infrastructure.",
      evidence: "Synthetic revisit model",
      lat: 36.944,
      lon: -76.342,
      status: "new"
    }
  ],
  "creech-afb": [
    {
      id: "ca-exa-1",
      source: "exa",
      severity: "medium",
      title: "Sparse but specific public references",
      summary: "Public web hits are fewer but contain specific facility and access-route language.",
      evidence: "Public web corpus",
      status: "new"
    },
    {
      id: "ca-sat-1",
      source: "satellite",
      severity: "high",
      title: "Clear-sky revisit concentration",
      summary: "Dummy weather and revisit assumptions create a stronger aerial collection window.",
      evidence: "Synthetic revisit model",
      lat: 36.586,
      lon: -115.677,
      status: "new"
    },
    {
      id: "ca-strava-1",
      source: "strava",
      severity: "medium",
      title: "Route-edge heat signature",
      summary: "Mock movement heat suggests recurring activity along an approach route.",
      evidence: "Mock heatmap tile summary",
      lat: 36.593,
      lon: -115.649,
      status: "new"
    }
  ]
};

function buildGenericFindings(target: MissionTarget): Finding[] {
  return [
    {
      id: `${target.id}-public-1`,
      source: "exa",
      severity: "medium",
      title: "Public context requires review",
      summary: "Ad hoc location lookup created a mock public-source review item for command triage.",
      evidence: "Mapbox geocoded location",
      lat: target.lat,
      lon: target.lon,
      status: "new",
    },
    {
      id: `${target.id}-revisit-1`,
      source: "satellite",
      severity: "low",
      title: "Generic revisit envelope staged",
      summary: "Synthetic revisit and movement layers were generated around the requested location.",
      evidence: "Synthetic fallback model",
      status: "reviewing",
    },
  ];
}

export function createMockReportForTarget(target: MissionTarget): MissionReport {
  const findings = findingsByTarget[target.id] ?? buildGenericFindings(target);
  const highCount = findings.filter((finding) => finding.severity === "high").length;
  const mediumCount = findings.filter((finding) => finding.severity === "medium").length;
  const aggregate = Math.min(92, 42 + highCount * 17 + mediumCount * 8);

  return {
    runId: `run-${target.id}-${Date.now().toString(36)}`,
    target,
    generatedAt: new Date().toISOString(),
    mode: "demo",
    score: {
      aggregate,
      movement: target.id === "fort-liberty" ? 78 : 55,
      personnel: target.id === "norfolk-naval" ? 66 : 48,
      facility: target.id === "creech-afb" ? 74 : 61,
      aerial: target.id === "fort-liberty" ? 82 : 69
    },
    findings,
    layers: buildLayersForTarget(target),
    narrative:
      `${target.name} shows a defensible but non-trivial public exposure profile. ` +
      "The strongest signals are repeatability, public context around operational tempo, and collection-window overlap. " +
      "The command review should focus on reducing predictable signatures, validating public-source assumptions, and documenting human decisions in the ontology.",
    mitigationPriorities: [
      "Review public movement signatures near route anchors.",
      "Validate public aircraft tracks against operational schedules.",
      "Stage high-severity findings for human review before action.",
      "Sync assessment, evidence, and review state into Palantir AIP."
    ],
    aip: {
      state: "not_synced"
    }
  };
}

export function createMockReport(targetId: string): MissionReport {
  const target = targets.find((item) => item.id === targetId) ?? targets[0];
  return createMockReportForTarget(target);
}
