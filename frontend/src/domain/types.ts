export type Severity = "critical" | "high" | "medium" | "low";

export type CollectorSource = "adsb" | "exa" | "satellite" | "strava" | "palantir" | "mapbox" | "system";

export type TaskState = "queued" | "running" | "complete" | "blocked";

export type AgentStatus = "idle" | "listening" | "working" | "complete" | "blocked";

export type SyncState = "not_synced" | "syncing" | "synced" | "failed";

export interface MissionTarget {
  id: string;
  name: string;
  lat: number;
  lon: number;
  radiusKm: number;
  theater: string;
}

export interface MissionScore {
  aggregate: number;
  movement: number;
  personnel: number;
  facility: number;
  aerial: number;
}

export interface Finding {
  id: string;
  source: CollectorSource;
  severity: Severity;
  title: string;
  summary: string;
  evidence: string;
  lat?: number;
  lon?: number;
  status: "new" | "reviewing" | "reviewed";
}

export interface MapLayer {
  id: string;
  source: CollectorSource;
  label: string;
  type: "column" | "heatmap" | "path" | "marker" | "polygon" | "footprint";
  visible: boolean;
  count: number;
  tone: "green" | "amber" | "red" | "blue";
  data: Array<Record<string, unknown>>;
}

export interface TaskEvent {
  id: string;
  at: string;
  agent: string;
  state: TaskState;
  message: string;
}

export interface ConversationMessage {
  id: string;
  role: "operator" | "voice-agent" | "system";
  text: string;
  at: string;
}

export interface AgentDescriptor {
  id: string;
  name: string;
  role: string;
  status: AgentStatus;
  currentTask: string;
}

export interface AipSyncReceipt {
  state: SyncState;
  objectRid?: string;
  actionName?: string;
  operationId?: string;
  lastSyncedAt?: string;
}

export interface MissionReport {
  runId: string;
  target: MissionTarget;
  generatedAt: string;
  mode: "demo" | "live";
  score: MissionScore;
  findings: Finding[];
  layers: MapLayer[];
  narrative: string;
  mitigationPriorities: string[];
  aip: AipSyncReceipt;
}
