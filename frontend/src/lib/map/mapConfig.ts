import type { MapViewState } from "@deck.gl/core";

import type { LocationInput } from "@/types/findings";

export const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";
export const MAPBOX_STYLE =
  process.env.NEXT_PUBLIC_MAPBOX_STYLE ?? "mapbox://styles/mapbox/dark-v11";

export const DEFAULT_MAP_TARGET: LocationInput = {
  name: "Fort Liberty",
  lat: 35.1414,
  lon: -79.006,
  radius_km: 20
};

export function buildInitialViewState(target: LocationInput): MapViewState {
  return {
    latitude: target.lat,
    longitude: target.lon,
    zoom: radiusKmToZoom(target.radius_km),
    pitch: 38,
    bearing: -10
  };
}

function radiusKmToZoom(radiusKm: number) {
  const zoom = 12.8 - Math.log2(Math.max(radiusKm, 1));
  return clamp(zoom, 5, 12.8);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
