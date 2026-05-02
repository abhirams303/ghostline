from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.models.finding import Finding
from app.models.location import LocationInput
from app.models.report import AnalyzeResponse, MapLayerPayload
from app.synthesis.scorer import score_findings


RUN_STREAMS: dict[str, list[str]] = {}


def _build_narrative(target: LocationInput, findings: list[Finding]) -> str:
    ordered = sorted(findings, key=lambda item: item.severity)
    bullets = "; ".join(f"{item.source}: {item.title.lower()}" for item in ordered[:4])
    return (
        f"Public traces around {target.name} suggest observable movement, facility, and timing signals. "
        f"Most immediate indicators: {bullets}. Mitigate by tightening geotag discipline, travel routine exposure, "
        f"and publish-time controls."
    )


async def synthesize_report(
    target: LocationInput,
    mode: str,
    findings: list[Finding],
    layers: list[MapLayerPayload],
) -> AnalyzeResponse:
    await asyncio.sleep(0)

    run_id = uuid4().hex
    narrative = _build_narrative(target, findings)
    RUN_STREAMS[run_id] = [
        f"Assessing exposure around {target.name}...",
        "Correlating movement and aerial patterns...",
        narrative,
    ]

    return AnalyzeResponse(
        run_id=run_id,
        target=target,
        mode=mode,
        generated_at=datetime.now(timezone.utc),
        score=score_findings(findings),
        findings=findings,
        layers=layers,
        narrative_preview=narrative,
    )


async def stream_run(run_id: str):
    for chunk in RUN_STREAMS.get(run_id, ["No narrative available for this run."]):
        yield chunk
