export type Severity = "low" | "medium" | "high" | "critical";
export type SourceName = "strava" | "adsb" | "satellite" | "exa" | "system";
export type SourceHealthState =
  | "ok"
  | "disabled"
  | "missing_config"
  | "upstream_error"
  | "no_data";

export interface LocationInput {
  name: string;
  lat: number;
  lon: number;
  radius_km: number;
}

export interface AnalyzeRequest {
  target: LocationInput;
  mode: "demo" | "live";
  route: Array<{ lat: number; lon: number }>;
  unit_id?: string | null;
}

export interface Finding {
  source: SourceName;
  title: string;
  severity: Severity;
  summary: string;
  evidence_url?: string | null;
  geo?: { lat: number; lon: number } | null;
  ts?: string | null;
  metadata: Record<string, unknown>;
}

export interface ScoreBreakdown {
  movement: number;
  personnel: number;
  facility: number;
  aerial: number;
  aggregate: number;
}

export interface MapLayerPayload {
  id: string;
  type: "heatmap" | "path" | "marker" | "polygon" | "footprint";
  visible: boolean;
  data: Array<Record<string, unknown>>;
}

export interface SourceStatus {
  source: "strava" | "adsb" | "satellite" | "exa";
  status: SourceHealthState;
  message: string;
  details: Record<string, string | number | boolean | null>;
}

export interface AnalyzeResponse {
  run_id: string;
  target: LocationInput;
  mode: "demo" | "live";
  generated_at: string;
  score: ScoreBreakdown;
  findings: Finding[];
  layers: MapLayerPayload[];
  source_statuses: SourceStatus[];
  narrative_preview: string;
  ethics_banner: string;
}
