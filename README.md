# GHOSTLINE

**Voice-driven cascade intelligence on Palantir Foundry.**

3rd Annual National Security Hackathon — Cerebral Valley × US Army xTech, May 2-3, 2026
Problem Statement 5: General National Security

## The Problem

Six weeks ago a French naval officer's Strava jog exposed the aircraft carrier Charles de Gaulle in a war zone. Last month 519 UK military personnel were exposed at nuclear submarine bases through fitness app data. The current fix is a memo telling soldiers to disable their apps. That is not a system.

## What We Built

A Palantir Foundry-native intelligence backbone that automatically assesses how surface-level OPSEC exposure (Strava, ADS-B, satellite imagery) propagates through linked military entities to compromise higher-order operational intelligence.

Two AI agents pre-compute cascade analysis and adversary predictions, writing their findings directly into the Palantir ontology. A Pipecat voice agent retrieves this pre-computed intelligence in milliseconds. A deck.gl tactical map visualizes the cascade.

Every fact has a source URL. Every analysis is auditable.

## Architecture

```
Real OSINT Sources -> Palantir Ontology (145 objects with provenance)
                              |
            Cascade Analyst Agent (GPT-4) -> CascadeRisk objects
                              |
          Adversary Modeler Agent (GPT-4) -> AdversaryAction objects
                              |
              Query API + HTTP Bridge (FastAPI on :8765)
                              |
              Pipecat Voice Agent + deck.gl Command Deck
```

## Palantir Foundry Ontology

| Object Type | Count |
|-------------|-------|
| GhostlineGeoFeature | 5 |
| GhostlineUnit | 36 |
| GhostlinePlatform | 11 |
| GhostlineSensor | 72 |
| OpsecAssessment | 5 |
| CascadeRisk | 5 |
| AdversaryAction | 11 |
| **Total** | **145** |

Norfolk's cascade reaches a chain depth of 94, traversing 7 Arleigh Burke destroyers, 2 Nimitz carriers, and named sensor systems including AN/SPY-1 and AN/SPQ-9. Joint Base Lewis-McChord's surface score of 42 (MEDIUM) escalates to 86 (HIGH) once propagation through linked entities is computed.

## Data Sources

- Wikipedia + Wikidata (military structure, unit assignments, sensor specs)
- Exa.ai (semantic OSINT search)
- OpenStreetMap Nominatim (geocoding)
- FlightRadar24 (live aircraft positions)
- CelesTrak (Sentinel satellite TLEs via skyfield)
- Palantir Foundry (ontology backbone)

## Sponsor Tools

- Palantir AIP (ontology, actions, links, AI FDE)
- OpenAI (threat brief generation, cascade analysis, adversary modeling)
- Exa.ai (OSINT search)
- deck.gl (tactical map visualization)
- Pipecat (voice agent framework)
- Deepgram (speech-to-text)
- Cartesia (text-to-speech)

## Repository Structure

- `backend/ai/` — Python intelligence backbone
  - `osint_populator.py` — populates ontology from public OSINT sources
  - `cascade_analyst.py` — AI agent: traverses ontology, writes CascadeRisk objects
  - `adversary_modeler.py` — AI agent: predicts adversary exploitation actions
  - `sensor_populator.py` — extracts sensor systems from Wikipedia platform pages
  - `query_api.py` — read-only consumer interface with fuzzy location matching
  - `voice_server.py` — FastAPI HTTP bridge (9 endpoints)
  - `realtime_enrichment.py` — FlightRadar24, CelesTrak, Exa.ai live data
  - `frontend_adapter.py` — transforms Palantir data into deck.gl frontend shape
  - `pipecat_tools.py` — voice agent tool definitions
  - `integrated_bot.py` — Pipecat agent with 5 intelligence tools
  - `demo_cache/` — pre-warmed offline cache for demo reliability

## Run

```bash
# Start the intelligence backend
cd forge && source venv/bin/activate
python3 -m uvicorn backend.ai.voice_server:app --port 8765

# Start the command deck frontend
cd bang_sec/command-deck && npm run dev

# Voice agent runs on Pipecat Cloud (gradient-bang-bot)
```

## Team

[Add names here]

## Demo Video

[Add link here]
