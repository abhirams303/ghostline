import { MAPBOX_TOKEN } from "../map/mapConfig";
import { API_BASE_URL } from "@/lib/api";

export interface GeocodedLocation {
  address?: string;
  bbox?: [number, number, number, number];
  category?: string;
  context: GeocodedContext[];
  features: GeocodedFeature[];
  id?: string;
  label: string;
  lat: number;
  lon: number;
  placeType: string;
  placeTypes: string[];
  query: string;
  relevance: number;
  text: string;
}

export interface GeocodedFeature {
  address?: string;
  bbox?: [number, number, number, number];
  category?: string;
  id?: string;
  label: string;
  lat: number;
  lon: number;
  placeType: string;
  placeTypes: string[];
  relevance: number;
  text: string;
}

export interface GeocodedContext {
  id?: string;
  shortCode?: string;
  text: string;
  type: string;
}

interface MapboxFeature {
  address?: string;
  bbox?: [number, number, number, number];
  center?: [number, number];
  context?: Array<{
    id?: string;
    short_code?: string;
    text?: string;
  }>;
  id?: string;
  place_name?: string;
  place_type?: string[];
  properties?: {
    category?: string;
  };
  relevance?: number;
  text?: string;
}

interface MapboxGeocodeResponse {
  features?: MapboxFeature[];
}

interface VoiceAssessmentLocationResponse {
  assessment_id?: string;
  location?: string;
  lat?: number;
  lon?: number;
}

interface BackendGeocodeResponse {
  id?: string | null;
  name: string;
  lat: number;
  lon: number;
  radius_km?: number;
  source?: string;
}

export async function geocodeLocationName(query: string): Promise<GeocodedLocation | null> {
  const trimmed = query.trim();
  if (!trimmed) {
    return null;
  }

  const voiceResult = await geocodeViaVoiceAssessment(trimmed);
  if (voiceResult) {
    return voiceResult;
  }

  const backendResult = await geocodeViaBackendGeocode(trimmed);
  if (backendResult) {
    return backendResult;
  }

  if (!MAPBOX_TOKEN) {
    return null;
  }

  const url = new URL(`https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(trimmed)}.json`);
  url.searchParams.set("access_token", MAPBOX_TOKEN);
  url.searchParams.set("autocomplete", "false");
  url.searchParams.set("language", "en");
  url.searchParams.set("limit", "5");
  url.searchParams.set("types", "address,poi,place,locality,neighborhood,region,district,country");

  const response = await fetch(url.toString());
  if (!response.ok) {
    return null;
  }

  const data = (await response.json()) as MapboxGeocodeResponse;
  const features = data.features?.map(mapFeature).filter((feature): feature is GeocodedFeature => feature !== null) ?? [];
  const feature = features[0];
  if (!feature) {
    return null;
  }

  const rawFeature = data.features?.[0];
  const context: GeocodedContext[] =
    rawFeature?.context
      ?.map((item) => {
        const text = item.text?.trim();
        if (!text) {
          return null;
        }

        return {
          text,
          type: item.id?.split(".")[0] ?? "context",
          ...(item.id ? { id: item.id } : {}),
          ...(item.short_code ? { shortCode: item.short_code } : {}),
        } satisfies GeocodedContext;
      })
      .filter((item): item is GeocodedContext => item !== null) ?? [];

  return {
    ...feature,
    context,
    features,
    query: trimmed,
  };
}

async function geocodeViaVoiceAssessment(query: string): Promise<GeocodedLocation | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/voice/get_assessment?location=${encodeURIComponent(query)}`);
    if (!response.ok) {
      return null;
    }

    const result = (await response.json()) as VoiceAssessmentLocationResponse;
    const lat = result.lat;
    const lon = result.lon;
    if (typeof lat !== "number" || typeof lon !== "number" || !Number.isFinite(lat) || !Number.isFinite(lon)) {
      return null;
    }

    const label = result.location || query;
    return buildGeocodedLocation({
      id: result.assessment_id,
      label,
      lat,
      lon,
      placeType: "voice-assessment",
      query,
      relevance: 0.9,
    });
  } catch {
    return null;
  }
}

async function geocodeViaBackendGeocode(query: string): Promise<GeocodedLocation | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/geocode?q=${encodeURIComponent(query)}`);
    if (!response.ok) {
      return null;
    }

    const result = (await response.json()) as BackendGeocodeResponse;
    const lat = result.lat;
    const lon = result.lon;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return null;
    }

    return buildGeocodedLocation({
      id: result.id ?? undefined,
      label: result.name || query,
      lat,
      lon,
      placeType: result.source ?? "backend-geocode",
      query,
      relevance: 0.86,
    });
  } catch {
    return null;
  }
}

function buildGeocodedLocation({
  id,
  label,
  lat,
  lon,
  placeType,
  query,
  relevance,
}: {
  id?: string | null;
  label: string;
  lat: number;
  lon: number;
  placeType: string;
  query: string;
  relevance: number;
}): GeocodedLocation {
  const feature: GeocodedFeature = {
    id: id ?? undefined,
    label,
    lat,
    lon,
    placeType,
    placeTypes: [placeType],
    relevance,
    text: label,
  };

  return {
    ...feature,
    context: [
      {
        text: placeType,
        type: "source",
      },
    ],
    features: [feature],
    query,
  };
}

function mapFeature(feature: MapboxFeature): GeocodedFeature | null {
  const center = feature?.center;
  if (!center || center.length < 2) {
    return null;
  }

  const label = feature.place_name ?? feature.text ?? "Mapbox result";
  const placeTypes = feature.place_type?.filter(Boolean) ?? ["feature"];

  return {
    address: feature.address,
    bbox: feature.bbox,
    category: feature.properties?.category,
    id: feature.id,
    label,
    lat: center[1],
    lon: center[0],
    placeType: placeTypes[0] ?? "feature",
    placeTypes,
    relevance: typeof feature.relevance === "number" ? feature.relevance : 0.72,
    text: feature.text ?? label,
  };
}
