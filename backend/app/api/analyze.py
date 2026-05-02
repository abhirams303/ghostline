import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.collectors.adsb import ADSBCollector
from app.collectors.exa import ExaCollector
from app.collectors.satellite import SatelliteCollector
from app.collectors.strava import StravaCollector
from app.config import get_settings
from app.models.location import AnalyzeRequest
from app.models.report import AnalyzeResponse
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

    results = await asyncio.gather(*(collector.collect(request) for collector in collectors))
    findings = [finding for collector_findings, _ in results for finding in collector_findings]
    layers = [layer for _, collector_layers in results for layer in collector_layers]

    if not findings and settings.use_demo_cache:
        cached = load_cached_report(request.target.name)
        if cached:
            return cached

    if not findings:
        raise HTTPException(status_code=404, detail="No findings were generated for this request.")

    run_id = uuid4().hex
    response = await synthesize_report(
        request.target,
        request.mode,
        findings,
        layers,
        run_id=run_id,
    )
    await asyncio.to_thread(
        persist_analysis_run,
        settings.database_path,
        request,
        response,
    )
    return response
