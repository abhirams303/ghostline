# OPSEC Mirror Backend

FastAPI service for analysis orchestration, live collector fan-out, scoring, and OpenAI-backed threat-brief synthesis with local fallback behavior.

Utility endpoints:

- `GET /geocode?q=<location>` resolves a free-form location string through OpenStreetMap Nominatim and returns the backend `LocationInput` shape.

Current live source coverage:

- ADS-B Exchange snapshot collector
- Exa news/public-web search collector

Current scaffold-only sources:

- Strava
- Satellite revisit
