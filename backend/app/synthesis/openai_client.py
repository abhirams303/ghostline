import json

from openai import AsyncOpenAI

from app.config import Settings
from app.models.finding import Finding
from app.models.location import LocationInput
from app.models.report import ScoreBreakdown
from app.synthesis.prompts import SYSTEM_PROMPT, build_synthesis_input


def _serialize_findings(findings: list[Finding]) -> str:
    return json.dumps(
        [
            {
                "source": finding.source,
                "title": finding.title,
                "severity": finding.severity,
                "summary": finding.summary,
                "evidence_url": finding.evidence_url,
                "geo": finding.geo.model_dump() if finding.geo else None,
                "timestamp": finding.ts.isoformat() if finding.ts else None,
            }
            for finding in findings
        ],
        indent=2,
    )


def _format_score(score: ScoreBreakdown) -> str:
    return (
        f"aggregate={score.aggregate}, movement={score.movement}, personnel={score.personnel}, "
        f"facility={score.facility}, aerial={score.aerial}"
    )


async def generate_threat_brief(
    settings: Settings,
    target: LocationInput,
    mode: str,
    score: ScoreBreakdown,
    findings: list[Finding],
) -> str | None:
    if not settings.openai_api_key:
        return None

    input_text = build_synthesis_input(
        target_name=target.name,
        mode=mode,
        score_summary=_format_score(score),
        serialized_findings=_serialize_findings(findings),
    )

    async with AsyncOpenAI(api_key=settings.openai_api_key) as client:
        response = await client.responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_PROMPT,
            input=input_text,
        )

    output_text = response.output_text.strip()
    return output_text or None
