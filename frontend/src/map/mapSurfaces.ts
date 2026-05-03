import { createTargetContextReport } from "../data/locationContextReport";
import { targets } from "../data/mockMission";
import type { MissionReport, MissionTarget } from "../domain/types";
import { buildInitialViewState } from "./mapConfig";

export interface MapSurfaceDefinition {
  id: string;
  order: number;
  label: string;
  target: MissionTarget;
  report: MissionReport;
  viewState: ReturnType<typeof buildInitialViewState>;
}

export const mapSurfaces: MapSurfaceDefinition[] = targets.map((target, index) => {
  const report = createTargetContextReport(target);

  return {
    id: target.id,
    order: index + 1,
    label: target.name,
    target,
    report,
    viewState: buildInitialViewState(target),
  };
});

export const defaultMapSurfaceId = mapSurfaces[0]?.id ?? "fort-liberty";

export function getMapSurface(surfaceId: string, surfaces = mapSurfaces): MapSurfaceDefinition {
  return surfaces.find((surface) => surface.id === surfaceId) ?? surfaces[0] ?? mapSurfaces[0];
}

export function getVisibleLayerIds(report: MissionReport): string[] {
  return report.layers.filter((layer) => layer.visible).map((layer) => layer.id);
}

const surfaceAliases: Record<string, string[]> = {
  "fort-liberty": ["fort liberty", "liberty", "ft liberty", "fort bragg", "bragg"],
  "norfolk-naval": ["norfolk naval", "norfolk", "naval station norfolk", "naval"],
  "creech-afb": ["creech afb", "creech", "creech air force base", "air force base creech"],
  jblm: ["jblm", "joint base lewis mcchord", "lewis mcchord", "lewis-mcchord", "fort lewis"],
  "naval-base-san-diego": ["naval base san diego", "san diego", "nbsd", "32nd street naval station"],
  shack15: ["shack15", "shack 15", "shack fifteen"],
};

const mapIntentPatterns = [
  /\b(map|surface|show|display|switch|open|focus|zoom|navigate|move|location|about|check|inspect|look)\b/,
  /\bgo\s+to\b/,
  /\bgoto\b/,
  /\bchange\s+(?:the\s+)?location\b/,
  /\bshow\s+me\b/,
];

const locationQueryPatterns = [
  /\b(?:go\s+to|goto|move\s+to|navigate\s+to|open|focus\s+(?:on\s+)?|zoom\s+(?:to|into)|show\s+me|show|display|switch\s+to|change\s+(?:the\s+)?location\s+to|set\s+(?:the\s+)?location\s+to|what\s+about|about|check|inspect|look\s+at|analyze|assess)\s+(.+)$/i,
  /\bwhere\s+is\s+(.+)$/i,
];

export function resolveTargetCommand(command: string): string | null {
  const normalized = normalizeCommand(command);
  const byName = mapSurfaces.find((surface) => surfaceMatchesCommand(surface, normalized));

  return byName?.target.id ?? null;
}

export function resolveExactTargetCommand(command: string, surfaces = mapSurfaces): string | null {
  const normalized = normalizeCommand(command);
  if (!normalized) {
    return null;
  }

  const byName = surfaces.find((surface) =>
    getSurfaceAliases(surface).some((alias) => normalizeCommand(alias) === normalized)
  );

  return byName?.target.id ?? null;
}

export function resolveMapSurfaceCommand(command: string): string | null {
  const normalized = normalizeCommand(command);
  const wantsMap = mapIntentPatterns.some((pattern) => pattern.test(normalized));

  if (!wantsMap) {
    return null;
  }

  const byName = mapSurfaces.find((surface) => surfaceMatchesCommand(surface, normalized));
  if (byName) {
    return byName.id;
  }

  const ordinalMatch =
    normalized.match(/\bmap\s+(one|1|first)\b/) ??
    normalized.match(/\b(one|1|first)\s+map\b/);
  if (ordinalMatch) {
    return mapSurfaces[0]?.id ?? null;
  }

  const secondMatch =
    normalized.match(/\bmap\s+(two|2|second)\b/) ??
    normalized.match(/\b(two|2|second)\s+map\b/);
  if (secondMatch) {
    return mapSurfaces[1]?.id ?? null;
  }

  const thirdMatch =
    normalized.match(/\bmap\s+(three|3|third)\b/) ??
    normalized.match(/\b(three|3|third)\s+map\b/);
  if (thirdMatch) {
    return mapSurfaces[2]?.id ?? null;
  }

  const fourthMatch =
    normalized.match(/\bmap\s+(four|4|fourth)\b/) ??
    normalized.match(/\b(four|4|fourth)\s+map\b/);
  if (fourthMatch) {
    return mapSurfaces[3]?.id ?? null;
  }

  const fifthMatch =
    normalized.match(/\bmap\s+(five|5|fifth)\b/) ??
    normalized.match(/\b(five|5|fifth)\s+map\b/);
  if (fifthMatch) {
    return mapSurfaces[4]?.id ?? null;
  }

  const sixthMatch =
    normalized.match(/\bmap\s+(six|6|sixth)\b/) ??
    normalized.match(/\b(six|6|sixth)\s+map\b/);
  if (sixthMatch) {
    return mapSurfaces[5]?.id ?? null;
  }

  return null;
}

export function extractLocationQuery(command: string): string | null {
  const normalized = normalizeCommand(command);
  if (!normalized) {
    return null;
  }

  for (const pattern of locationQueryPatterns) {
    const match = normalized.match(pattern);
    const candidate = cleanupLocationQuery(match?.[1] ?? "");
    if (candidate) {
      return candidate;
    }
  }

  const hasKnownCommand =
    /\b(push|sync|review|compare|aip|finding|findings|help|status|voice|microphone|mic)\b/.test(normalized);
  const looksLikeBarePlace =
    !hasKnownCommand &&
    normalized.split(/\s+/).length <= 5 &&
    normalized.length >= 3 &&
    !/^(hi|hello|hey|thanks|thank you|yes|no|okay|ok|stop|cancel)$/.test(normalized);

  return looksLikeBarePlace ? cleanupLocationQuery(normalized) : null;
}

function normalizeCommand(command: string): string {
  return command.toLowerCase().replace(/[^\w\s-]/g, " ").replace(/\s+/g, " ").trim();
}

function cleanupLocationQuery(query: string): string | null {
  const cleaned = query
    .replace(/\b(?:map|surface|location|please|now|for me|here)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();

  return cleaned.length >= 3 ? cleaned : null;
}

function surfaceMatchesCommand(surface: MapSurfaceDefinition, normalizedCommand: string): boolean {
  return getSurfaceAliases(surface).some((alias) => hasPhrase(normalizedCommand, alias));
}

function getSurfaceAliases(surface: MapSurfaceDefinition): string[] {
  const targetName = surface.target.name.toLowerCase();
  const shortName = targetName.split(/\s+/)[0];
  return [targetName, shortName, ...(surfaceAliases[surface.id] ?? [])];
}

function hasPhrase(normalizedCommand: string, phrase: string): boolean {
  const normalizedPhrase = normalizeCommand(phrase);
  if (!normalizedPhrase) {
    return false;
  }

  const escaped = normalizedPhrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  return new RegExp(`(^|\\s)${escaped}(?=\\s|$)`).test(normalizedCommand);
}
