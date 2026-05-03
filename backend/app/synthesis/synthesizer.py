from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from app.config import get_settings
from app.models.finding import Finding
from app.models.location import LocationInput
from app.models.report import (
    AnalyzeResponse,
    MapLayerPayload,
    ScoreBreakdown,
    SourceStatus,
)
from app.synthesis.openai_client import generate_threat_brief
from app.synthesis.scorer import score_findings

RUN_STREAMS: dict[str, list[str]] = {}


def _build_fallback_narrative(
    target: LocationInput,
    findings: list[Finding],
    score: ScoreBreakdown,
    source_statuses: list[SourceStatus],
) -> str:
    ordered = sorted(findings, key=lambda item: item.severity)
    bullets = "; ".join(f"{item.source}: {item.title.lower()}" for item in ordered[:4])
    degraded = [
        status.source
        for status in source_statuses
        if status.status not in {"ok", "no_data"}
    ]
    degraded_note = ""
    if degraded:
        degraded_note = f" Source health warnings: {', '.join(source.upper() for source in degraded)}."
    return (
        f"Public traces around {target.name} indicate an aggregate exposure score of {score.aggregate}. "
        f"Most immediate indicators: {bullets}. Based on the observed public signals, prioritize geotag discipline, "
        f"travel routine disruption, and publish-time controls.{degraded_note}"
    )


def _chunk_narrative(narrative: str) -> list[str]:
    chunks = [
        chunk.strip()
        for chunk in re.split(r"(?<=[.!?])\s+", narrative)
        if chunk.strip()
    ]
    return chunks or [narrative]


async def synthesize_report(
    target: LocationInput,
    mode: Literal["demo", "live"],
    findings: list[Finding],
    layers: list[MapLayerPayload],
    source_statuses: list[SourceStatus] | None = None,
    run_id: str | None = None,
) -> AnalyzeResponse:
    settings = get_settings()
    score = score_findings(findings)
    source_statuses = source_statuses or []

    run_id = run_id or uuid4().hex
    try:
        narrative = await generate_threat_brief(settings, target, mode, score, findings)
    except Exception:
        narrative = None

    if not narrative:
        narrative = _build_fallback_narrative(target, findings, score, source_statuses)

    RUN_STREAMS[run_id] = [
        f"Assessing exposure around {target.name}..."
    ] + _chunk_narrative(narrative)

    return AnalyzeResponse(
        run_id=run_id,
        target=target,
        mode=mode,
        generated_at=datetime.now(timezone.utc),
        score=score,
        findings=findings,
        layers=layers,
        source_statuses=source_statuses,
        narrative_preview=narrative,
    )


async def stream_run(run_id: str):
    for chunk in RUN_STREAMS.get(run_id, ["No narrative available for this run."]):
        yield chunk
