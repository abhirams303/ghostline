from app.models.report import AnalyzeResponse


class AIPClient:
    async def push_report(self, report: AnalyzeResponse) -> dict[str, str]:
        return {
            "status": "not_configured",
            "message": "AIP Ontology wiring is intentionally left as a thin placeholder in this scaffold.",
        }
