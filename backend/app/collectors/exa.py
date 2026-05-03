from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.models.finding import Finding
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload


def _truncate_text(value: str, limit: int = 320) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class ExaCollector(BaseCollector):
    source = "exa"

    @staticmethod
    def _build_query(request: AnalyzeRequest) -> str:
        base = (
            f'"{request.target.name}" public reporting activity exercise operations personnel travel '
            "social media news"
        )
        if request.unit_id:
            base += f' "{request.unit_id}"'
        return base

    async def _search_payload(self, request: AnalyzeRequest) -> dict[str, Any]:
        settings = get_settings()
        start_published = (datetime.now(timezone.utc) - timedelta(days=settings.exa_lookback_days)).isoformat()
        payload = {
            "query": self._build_query(request),
            "type": "auto",
            "category": "news",
            "numResults": settings.exa_num_results,
            "startPublishedDate": start_published,
            "contents": {
                "highlights": {
                    "maxCharacters": settings.exa_highlights_max_characters,
                }
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.exa_base_url.rstrip('/')}/search",
                headers={
                    "x-api-key": settings.exa_api_key or "",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("results")
        if isinstance(results, list):
            return results
        return []

    def _build_findings(
        self,
        payload: dict[str, Any],
        results: list[dict[str, Any]],
    ) -> list[Finding]:
        findings: list[Finding] = []
        request_id = payload.get("requestId")

        for rank, result in enumerate(results, start=1):
            title = result.get("title") or "Untitled result"
            url = result.get("url")
            published_date = result.get("publishedDate")
            highlights = result.get("highlights") or []
            summary = result.get("summary")
            text = result.get("text")

            snippet = None
            if isinstance(summary, str) and summary.strip():
                snippet = summary
            elif isinstance(highlights, list) and highlights:
                snippet = highlights[0]
            elif isinstance(text, str) and text.strip():
                snippet = text
            else:
                snippet = "Exa returned a result linked to the target, but no highlight text was available."

            severity = "medium" if rank == 1 else "low"
            findings.append(
                Finding(
                    source="exa",
                    title=title,
                    severity=severity,
                    summary=_truncate_text(snippet),
                    evidence_url=url,
                    ts=datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                    if isinstance(published_date, str) and published_date
                    else datetime.now(timezone.utc),
                    metadata={
                        "collector": self.source,
                        "request_id": request_id,
                        "document_id": result.get("id"),
                        "document_title": title,
                        "canonical_url": url,
                        "published_at": published_date,
                        "author": result.get("author"),
                        "rank": rank,
                    },
                )
            )

        return findings

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        settings = get_settings()
        if not settings.exa_enabled or not settings.exa_api_key:
            return [], []

        try:
            payload = await self._search_payload(request)
        except httpx.HTTPError:
            return [], []

        results = self._extract_results(payload)
        if not results:
            return [], []

        return self._build_findings(payload, results), []
