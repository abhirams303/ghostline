import { API_BASE_URL, analyzeTarget } from "@/lib/api";
import type { AnalyzeResponse, Finding as BackendFinding, MapLayerPayload, SourceName } from "@/types/findings";

import { createTargetContextReport } from "../data/locationContextReport";
import { targets } from "../data/mockMission";
import type {
  AipSyncReceipt,
  CollectorSource,
  Finding,
  MapLayer,
  MissionReport,
  MissionTarget,
  Severity,
} from "../domain/types";

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export interface PalantirBackend {
  listTargets(): Promise<MissionTarget[]>;
  runAssessment(targetId: string): Promise<MissionReport>;
  syncAssessment(report: MissionReport): Promise<AipSyncReceipt>;
  markFindingReviewed(report: MissionReport, findingId: string): Promise<MissionReport>;
  askAip(report: MissionReport, prompt: string): Promise<string>;
}

interface VoiceAssessment {
  location: string;
  exposure_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  strava_score: number;
  aircraft_score: number;
  satellite_score: number;
  brief: string;
  lat: number;
  lon: number;
  assessment_id?: string;
  assessment_timestamp?: string;
  foundry_url?: string;
}

export class GhostlineBackend implements PalantirBackend {
  async listTargets(): Promise<MissionTarget[]> {
    await wait(80);
    return targets;
  }

  async runAssessment(targetId: string): Promise<MissionReport> {
    const target = targets.find((item) => item.id === targetId) ?? targets[0];
    const voiceReport = await fetchVoiceAssessment(target);
    if (voiceReport) {
      return mapVoiceAssessment(target, voiceReport);
    }

    const backendReport = await fetchAnalyzeReport(target);
    if (backendReport) {
      return mapAnalyzeResponse(backendReport);
    }

    return createTargetContextReport(target);
  }

  async syncAssessment(report: MissionReport): Promise<AipSyncReceipt> {
    await wait(420);
    return {
      state: "synced",
      objectRid: `ri.ghostline.command-deck.${report.runId}`,
      actionName: "syncOpsecAnalysisRun",
      operationId: `ri.actions.command-deck.${crypto.randomUUID()}`,
      lastSyncedAt: new Date().toISOString(),
    };
  }

  async markFindingReviewed(report: MissionReport, findingId: string): Promise<MissionReport> {
    await wait(180);
    return {
      ...report,
      findings: report.findings.map((finding) =>
        finding.id === findingId ? { ...finding, status: "reviewed" } : finding
      ),
    };
  }

  async askAip(report: MissionReport, prompt: string): Promise<string> {
    await wait(260);
    const topFinding = report.findings[0];
    if (prompt.toLowerCase().includes("compare")) {
      return "AIP draft: comparison data is available through the voice server leaderboard once Foundry is configured.";
    }
    if (topFinding) {
      return `AIP draft: ${report.target.name} has exposure score ${report.score.aggregate}. Top review item: ${topFinding.title}.`;
    }
    return "AIP draft: no findings are loaded for the active command-deck run.";
  }
}

async function fetchVoiceAssessment(target: MissionTarget): Promise<VoiceAssessment | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/voice/get_assessment?location=${encodeURIComponent(target.name)}`);
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as unknown;
    return isVoiceAssessment(payload) ? payload : null;
  } catch {
    return null;
  }
}

async function fetchAnalyzeReport(target: MissionTarget): Promise<AnalyzeResponse | null> {
  try {
    return await analyzeTarget({
      target: {
        name: target.name,
        lat: target.lat,
        lon: target.lon,
        radius_km: target.radiusKm,
      },
      mode: "live",
      route: [],
      unit_id: null,
    });
  } catch {
    return null;
  }
}

function mapVoiceAssessment(target: MissionTarget, report: VoiceAssessment): MissionReport {
  const base = createTargetContextReport({
    ...target,
    name: report.location || target.name,
    lat: report.lat || target.lat,
    lon: report.lon || target.lon,
  });
  const generatedAt = report.assessment_timestamp ?? new Date().toISOString();
  const aggregate = clampScore(report.exposure_score);

  return {
    ...base,
    runId: report.assessment_id || `voice-${target.id}-${Date.now().toString(36)}`,
    generatedAt,
    score: {
      aggregate,
      movement: clampScore(report.strava_score),
      personnel: clampScore(Math.round((report.strava_score + report.aircraft_score) / 2)),
      facility: clampScore(report.satellite_score),
      aerial: clampScore(report.aircraft_score),
    },
    findings: [
      scoreFinding(target, "strava", "Movement exposure", report.strava_score),
      scoreFinding(target, "adsb", "Aircraft predictability", report.aircraft_score),
      scoreFinding(target, "satellite", "Satellite vulnerability", report.satellite_score),
    ],
    narrative:
      report.brief ||
      `${report.location || target.name} returned a ${report.risk_level} OPSEC posture from the voice assessment API.`,
    mitigationPriorities: [
      "Use voice commands to pivot the map before deeper review.",
      "Review the highest scoring layer before syncing an operational record.",
      "Keep Foundry writeback behind explicit human action.",
      report.foundry_url ? `Open Foundry assessment: ${report.foundry_url}` : "Attach Foundry provenance when available.",
    ],
    aip: {
      state: "not_synced",
      objectRid: report.assessment_id,
      operationId: report.foundry_url,
    },
  };
}

function isVoiceAssessment(value: unknown): value is VoiceAssessment {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as VoiceAssessment).location === "string" &&
    typeof (value as VoiceAssessment).exposure_score === "number" &&
    typeof (value as VoiceAssessment).strava_score === "number" &&
    typeof (value as VoiceAssessment).aircraft_score === "number" &&
    typeof (value as VoiceAssessment).satellite_score === "number"
  );
}

function mapAnalyzeResponse(response: AnalyzeResponse): MissionReport {
  const target: MissionTarget = {
    id: slugify(response.target.name),
    name: response.target.name,
    lat: response.target.lat,
    lon: response.target.lon,
    radiusKm: response.target.radius_km,
    theater: response.mode,
  };

  const base = createTargetContextReport(target);

  return {
    ...base,
    runId: response.run_id,
    generatedAt: response.generated_at,
    mode: response.mode,
    score: {
      aggregate: response.score.aggregate,
      movement: response.score.movement,
      personnel: response.score.personnel,
      facility: response.score.facility,
      aerial: response.score.aerial,
    },
    findings: response.findings.map(mapBackendFinding),
    layers: [...response.layers.map(mapBackendLayer), ...base.layers],
    narrative: response.narrative_preview,
    mitigationPriorities: response.source_statuses.map((status) => status.message),
  };
}

function mapBackendFinding(finding: BackendFinding, index: number): Finding {
  return {
    id: `${finding.source}-${slugify(finding.title)}-${index + 1}`,
    source: mapSource(finding.source),
    severity: finding.severity,
    title: finding.title,
    summary: finding.summary,
    evidence: finding.evidence_url ?? finding.ts ?? "Ghostline analysis response",
    lat: finding.geo?.lat,
    lon: finding.geo?.lon,
    status: "new",
  };
}

function mapBackendLayer(layer: MapLayerPayload): MapLayer {
  const source = sourceFromLayerId(layer.id);
  return {
    id: layer.id,
    source,
    label: labelForLayer(layer.id, source),
    type: layer.type,
    visible: layer.visible,
    count: layer.data.length,
    tone: toneForSource(source),
    data: layer.data,
  };
}

function scoreFinding(target: MissionTarget, source: CollectorSource, title: string, score: number): Finding {
  return {
    id: `${target.id}-${source}-score`,
    source,
    severity: severityForScore(score),
    title,
    summary: `${title} is scored at ${clampScore(score)}/100 for ${target.name}.`,
    evidence: "GHOSTLINE voice assessment",
    lat: target.lat,
    lon: target.lon,
    status: "new",
  };
}

function sourceFromLayerId(id: string): CollectorSource {
  const normalized = id.toLowerCase();
  if (normalized.includes("adsb")) return "adsb";
  if (normalized.includes("exa")) return "exa";
  if (normalized.includes("satellite")) return "satellite";
  if (normalized.includes("strava")) return "strava";
  return "system";
}

function mapSource(source: SourceName): CollectorSource {
  return source === "system" ? "system" : source;
}

function labelForLayer(id: string, source: CollectorSource): string {
  if (id.includes("tracks")) return "Aerial tracks";
  if (id.includes("markers")) return "Aerial markers";
  if (id.includes("heatmap")) return "Movement heat";
  if (id.includes("footprint")) return "Revisit footprint";
  return source.toUpperCase();
}

function toneForSource(source: CollectorSource): MapLayer["tone"] {
  switch (source) {
    case "adsb":
      return "amber";
    case "satellite":
      return "blue";
    case "strava":
      return "red";
    default:
      return "green";
  }
}

function severityForScore(score: number): Severity {
  if (score >= 85) return "critical";
  if (score >= 70) return "high";
  if (score >= 45) return "medium";
  return "low";
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(Number.isFinite(value) ? value : 0)));
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "target";
}

export const palantirBackend: PalantirBackend = new GhostlineBackend();
