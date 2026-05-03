import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.collectors.adsb import ADSBCollector
from app.collectors.exa import ExaCollector
from app.collectors.satellite import SatelliteCollector
from app.collectors.strava import StravaCollector
from app.config import get_settings
from app.models.location import AnalyzeRequest
from app.models.report import AnalyzeResponse, SourceStatus
from app.storage import persist_analysis_run
from app.synthesis.synthesizer import synthesize_report
from app.utils.cache import load_cached_report

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    settings = get_settings()

    if request.mode == "demo":
        cached = load_cached_report(request.target.name)
        if cached:
            return cached

    collectors = [
        StravaCollector(),
        ADSBCollector(),
        SatelliteCollector(),
        ExaCollector(),
    ]

    results = await asyncio.gather(
        *(collector.collect(request) for collector in collectors)
    )
    findings = [
        finding for collector_findings, _ in results for finding in collector_findings
    ]
    layers = [layer for _, collector_layers in results for layer in collector_layers]

    source_statuses: list[SourceStatus] = []
    for source in ("strava", "adsb", "satellite", "exa"):
        source_findings = [finding for finding in findings if finding.source == source]
        explicit_status = next(
            (
                finding.metadata.get("status")
                for finding in source_findings
                if isinstance(finding.metadata.get("status"), str)
            ),
            None,
        )
        if explicit_status in {
            "disabled",
            "missing_config",
            "upstream_error",
            "no_data",
            "ok",
        }:
            details = next(
                (
                    {
                        key: value
                        for key, value in finding.metadata.items()
                        if isinstance(value, (str, int, float, bool))
                        or value is None
                    }
                    for finding in source_findings
                    if finding.metadata.get("status") == explicit_status
                ),
                {},
            )
            details.setdefault("finding_count", len(source_findings))
            source_statuses.append(
                SourceStatus(
                    source=source,
                    status=explicit_status,
                    message=next(
                        (
                            finding.summary
                            for finding in source_findings
                            if finding.metadata.get("status") == explicit_status
                        ),
                        f"{source} collector reported {explicit_status}.",
                    ),
                    details=details,
                )
            )
            continue

        if source_findings:
            source_statuses.append(
                SourceStatus(
                    source=source,
                    status="ok",
                    message=f"{source.upper()} collector produced findings.",
                    details={"finding_count": len(source_findings)},
                )
            )
        else:
            source_statuses.append(
                SourceStatus(
                    source=source,
                    status="no_data",
                    message=f"{source.upper()} collector produced no findings.",
                    details={"finding_count": 0},
                )
            )

    if not findings and settings.use_demo_cache:
        cached = load_cached_report(request.target.name)
        if cached:
            return cached

    if not findings:
        raise HTTPException(
            status_code=404, detail="No findings were generated for this request."
        )

    run_id = uuid4().hex
    response = await synthesize_report(
        request.target,
        request.mode,
        findings,
        layers,
        source_statuses=source_statuses,
        run_id=run_id,
    )
    await asyncio.to_thread(
        persist_analysis_run,
        settings.database_path,
        request,
        response,
    )
    return response
