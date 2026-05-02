import type { LocationInput } from "@/types/findings";

const PRESET_TARGETS: Record<string, LocationInput> = {
  "fort liberty": { name: "Fort Liberty", lat: 35.1414, lon: -79.006, radius_km: 20 },
  "norfolk naval": { name: "Norfolk Naval", lat: 36.946, lon: -76.3306, radius_km: 18 },
  "creech afb": { name: "Creech AFB", lat: 36.5872, lon: -115.6767, radius_km: 25 }
};


export function resolveTarget(input: string): LocationInput {
  const key = input.trim().toLowerCase();
  return PRESET_TARGETS[key] ?? PRESET_TARGETS["fort liberty"];
}


export function listPresetTargets(): LocationInput[] {
  return Object.values(PRESET_TARGETS);
}
