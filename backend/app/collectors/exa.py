from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple, cast
from urllib.parse import urlparse

import httpx

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload

logger = logging.getLogger(__name__)

EXA_QUERY_FAMILIES: tuple[tuple[str, str], ...] = (
    ("identity", '"{target}"'),
    (
        "operations",
        '"{target}" public reporting activity exercise operations readiness deployment',
    ),
    (
        "personnel",
        '"{target}" personnel travel conference social media news',
    ),
    (
        "location",
        '"{target}" "{location}" operations facility community news',
    ),
    (
        "infrastructure",
        '"{target}" contractor vendor support infrastructure facility',
    ),
    (
        "unit",
        '"{target}" "{unit_id}" public reporting operations news',
    ),
)

TRUSTED_DOMAINS: tuple[str, ...] = (
    ".mil",
    ".gov",
    "defense.gov",
    "army.mil",
    "navy.mil",
    "af.mil",
)
NOISY_DOMAINS: tuple[str, ...] = ("facebook.com", "instagram.com")
KEYWORD_GROUPS: tuple[str, ...] = (
    "exercise",
    "operation",
    "readiness",
    "deployment",
    "travel",
    "personnel",
    "facility",
    "contractor",
    "vendor",
    "infrastructure",
    "news",
    "social",
)


class ExaQueryPlan(NamedTuple):
    family: str
    query: str
    category: str


class ExaCollectionStatus(NamedTuple):
    status: str
    message: str
    details: dict[str, str | int | float | bool | None]


class ExaNormalizedResult:
    document_id: str | None
    title: str
    url: str | None
    canonical_url: str | None
    domain: str | None
    published_at: datetime
    published_raw: str | None
    author: str | None
    snippet: str
    query_families: set[str]
    query_labels: list[str]
    categories: set[str]
    ranks: list[int]
    matched_unit_id: bool
    matched_target_name: bool
    relevance_score: int

    def __init__(
        self,
        document_id: str | None,
        title: str,
        url: str | None,
        canonical_url: str | None,
        domain: str | None,
        published_at: datetime,
        published_raw: str | None,
        author: str | None,
        snippet: str,
        query_families: set[str],
        query_labels: list[str],
        categories: set[str],
        ranks: list[int],
        matched_unit_id: bool,
        matched_target_name: bool,
        relevance_score: int,
    ) -> None:
        self.document_id = document_id
        self.title = title
        self.url = url
        self.canonical_url = canonical_url
        self.domain = domain
        self.published_at = published_at
        self.published_raw = published_raw
        self.author = author
        self.snippet = snippet
        self.query_families = query_families
        self.query_labels = query_labels
        self.categories = categories
        self.ranks = ranks
        self.matched_unit_id = matched_unit_id
        self.matched_target_name = matched_target_name
        self.relevance_score = relevance_score


def _truncate_text(value: str, limit: int = 320) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _parse_published_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _canonicalize_url(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value

    normalized_path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{normalized_path}"


def _parse_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc.lower() or None


def _safe_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


class ExaCollector(BaseCollector):
    source: str = "exa"

    @staticmethod
    def _build_queries(request: AnalyzeRequest) -> list[ExaQueryPlan]:
        settings = get_settings()
        plans: list[ExaQueryPlan] = []
        categories: list[str] = []
        if settings.exa_news_enabled:
            categories.append("news")
        if settings.exa_web_enabled:
            categories.append("auto")
        if not categories:
            categories.append("auto")

        request_context = {
            "target": request.target.name,
            "location": request.target.name,
            "unit_id": request.unit_id or request.target.name,
        }

        for family, template in EXA_QUERY_FAMILIES:
            if family == "unit" and not request.unit_id:
                continue
            query = template.format(**request_context).strip()
            for category in categories:
                plans.append(ExaQueryPlan(family, query, category))

        deduped_plans: list[ExaQueryPlan] = []
        seen: set[tuple[str, str]] = set()
        for plan in plans:
            key = (plan.query, plan.category)
            if key in seen:
                continue
            seen.add(key)
            deduped_plans.append(plan)

        return deduped_plans[: settings.exa_max_queries_per_run]

    async def _search_payload(self, request: AnalyzeRequest) -> dict[str, Any]:
        plans = self._build_queries(request)
        if not plans:
            return {"results": []}
        return await self._search_single_plan(request, plans[0])

    async def _search_single_plan(
        self,
        request: AnalyzeRequest,
        plan: ExaQueryPlan,
    ) -> dict[str, Any]:
        settings = get_settings()
        start_published = (
            datetime.now(timezone.utc) - timedelta(days=settings.exa_lookback_days)
        ).isoformat()
        payload = {
            "query": plan.query,
            "type": "auto",
            "category": plan.category,
            "numResults": settings.exa_num_results,
            "startPublishedDate": start_published,
            "contents": {
                "highlights": {
                    "maxCharacters": settings.exa_highlights_max_characters,
                }
            },
        }

        timeout = httpx.Timeout(settings.exa_timeout_seconds)
        last_error: Exception | None = None

        for attempt in range(settings.exa_retry_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{settings.exa_base_url.rstrip('/')}/search",
                        headers={
                            "x-api-key": settings.exa_api_key or "",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    result = cast(dict[str, Any], response.json())
                    result["_query_family"] = plan.family
                    result["_query"] = plan.query
                    result["_query_category"] = plan.category
                    logger.info(
                        "Exa query completed",
                        extra={
                            "collector": self.source,
                            "target": request.target.name,
                            "query_family": plan.family,
                            "query_category": plan.category,
                            "query": plan.query,
                            "attempt": attempt + 1,
                            "result_count": len(self._extract_results(result)),
                        },
                    )
                    return result
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                logger.warning(
                    "Exa query returned HTTP error",
                    extra={
                        "collector": self.source,
                        "target": request.target.name,
                        "query_family": plan.family,
                        "query_category": plan.category,
                        "status_code": status_code,
                        "attempt": attempt + 1,
                    },
                )
                if status_code not in {429, 500, 502, 503, 504}:
                    raise
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "Exa query transport error",
                    extra={
                        "collector": self.source,
                        "target": request.target.name,
                        "query_family": plan.family,
                        "query_category": plan.category,
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )

            if attempt < settings.exa_retry_attempts:
                await asyncio.sleep(settings.exa_retry_backoff_seconds * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError("Exa search failed without a captured exception.")

    @staticmethod
    def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        return []

    @staticmethod
    def _extract_snippet(result: dict[str, Any]) -> str:
        highlights_raw = result.get("highlights")
        summary = _safe_str(result.get("summary"))
        text = _safe_str(result.get("text"))

        if summary:
            return summary
        if isinstance(highlights_raw, list):
            for item in highlights_raw:
                highlight = _safe_str(item)
                if highlight:
                    return highlight
        if text:
            return text
        return "Exa returned a result linked to the target, but no highlight text was available."

    @staticmethod
    def _score_result(
        request: AnalyzeRequest,
        title: str,
        snippet: str,
        domain: str | None,
        query_family_count: int,
    ) -> tuple[int, bool, bool]:
        haystack = f"{title} {snippet}".lower()
        target_name = request.target.name.lower()
        matched_target_name = target_name in haystack
        matched_unit_id = bool(request.unit_id and request.unit_id.lower() in haystack)

        score = 0
        if matched_target_name:
            score += 3
        if matched_unit_id:
            score += 3
        score += sum(1 for keyword in KEYWORD_GROUPS if keyword in haystack)
        score += min(query_family_count, 3)

        if domain:
            if any(trusted in domain for trusted in TRUSTED_DOMAINS):
                score += 2
            elif any(noisy in domain for noisy in NOISY_DOMAINS):
                score -= 1

        return score, matched_target_name, matched_unit_id

    def _normalize_results(
        self,
        request: AnalyzeRequest,
        payloads: list[dict[str, Any]],
    ) -> list[ExaNormalizedResult]:
        aggregated: dict[str, ExaNormalizedResult] = {}

        for payload in payloads:
            query_family = str(payload.get("_query_family") or "unknown")
            query = str(payload.get("_query") or "")
            category = str(payload.get("_query_category") or "auto")

            for rank, result in enumerate(self._extract_results(payload), start=1):
                title = _safe_str(result.get("title")) or "Untitled result"
                url = _safe_str(result.get("url"))
                canonical_url = _canonicalize_url(url)
                snippet = _truncate_text(self._extract_snippet(result))
                published_raw = _safe_str(result.get("publishedDate"))
                published_at = _parse_published_date(published_raw) or datetime.now(
                    timezone.utc
                )
                domain = _parse_domain(canonical_url)
                document_id = _safe_str(result.get("id"))
                key = str(
                    document_id
                    or canonical_url
                    or f"{title}:{published_at.isoformat()}"
                )

                existing = aggregated.get(key)
                if existing is None:
                    aggregated[key] = ExaNormalizedResult(
                        document_id=document_id,
                        title=title,
                        url=url,
                        canonical_url=canonical_url,
                        domain=domain,
                        published_at=published_at,
                        published_raw=published_raw,
                        author=_safe_str(result.get("author")),
                        snippet=snippet,
                        query_families={query_family},
                        query_labels=[query],
                        categories={category},
                        ranks=[rank],
                        matched_unit_id=False,
                        matched_target_name=False,
                        relevance_score=0,
                    )
                    continue

                existing.query_families.add(query_family)
                if query and query not in existing.query_labels:
                    existing.query_labels.append(query)
                existing.categories.add(category)
                existing.ranks.append(rank)
                if len(snippet) > len(existing.snippet):
                    existing.snippet = snippet
                if existing.url is None:
                    existing.url = url
                if existing.canonical_url is None:
                    existing.canonical_url = canonical_url
                if existing.domain is None:
                    existing.domain = domain
                if existing.author is None:
                    existing.author = _safe_str(result.get("author"))
                if existing.document_id is None:
                    existing.document_id = document_id
                if published_at < existing.published_at:
                    existing.published_at = published_at
                    existing.published_raw = published_raw or existing.published_raw

        normalized_results = list(aggregated.values())
        for item in normalized_results:
            score, matched_target_name, matched_unit_id = self._score_result(
                request=request,
                title=item.title,
                snippet=item.snippet,
                domain=item.domain,
                query_family_count=len(item.query_families),
            )
            item.relevance_score = score
            item.matched_target_name = matched_target_name
            item.matched_unit_id = matched_unit_id

        settings = get_settings()
        filtered = [
            item
            for item in normalized_results
            if item.relevance_score >= settings.exa_min_relevance_score
        ]
        filtered.sort(
            key=lambda item: (
                -item.relevance_score,
                min(item.ranks) if item.ranks else 999,
                item.published_at,
            )
        )
        return filtered

    def _build_findings(
        self,
        request: AnalyzeRequest,
        request_ids: list[str],
        results: list[ExaNormalizedResult],
        status: ExaCollectionStatus,
    ) -> list[Finding]:
        if status.status in {"disabled", "missing_config", "upstream_error", "no_data"}:
            return [
                Finding(
                    source="exa",
                    title=(
                        "Exa collection unavailable"
                        if status.status != "no_data"
                        else "No public web evidence identified"
                    ),
                    severity="low",
                    summary=status.message,
                    evidence_url=None,
                    geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                    ts=datetime.now(timezone.utc),
                    metadata={
                        "collector": self.source,
                        "status": status.status,
                        **status.details,
                    },
                )
            ]

        findings: list[Finding] = []
        for index, result in enumerate(results, start=1):
            severity = "medium"
            if result.relevance_score >= 9:
                severity = "high"
            elif result.relevance_score < 6:
                severity = "low"

            findings.append(
                Finding(
                    source="exa",
                    title=result.title,
                    severity=severity,
                    summary=result.snippet,
                    evidence_url=result.canonical_url or result.url,
                    ts=result.published_at,
                    metadata={
                        "collector": self.source,
                        "status": "ok",
                        "request_ids": request_ids,
                        "document_id": result.document_id,
                        "document_title": result.title,
                        "canonical_url": result.canonical_url or result.url,
                        "published_at": result.published_raw
                        or result.published_at.isoformat(),
                        "author": result.author,
                        "rank": index,
                        "query_families": sorted(result.query_families),
                        "queries": result.query_labels,
                        "categories": sorted(result.categories),
                        "relevance_score": result.relevance_score,
                        "matched_target_name": result.matched_target_name,
                        "matched_unit_id": result.matched_unit_id,
                        "domain": result.domain,
                        "query_family_count": len(result.query_families),
                    },
                )
            )

        return findings

    async def _collect_payloads(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[dict[str, Any]], ExaCollectionStatus]:
        settings = get_settings()
        if not settings.exa_enabled:
            return [], ExaCollectionStatus(
                status="disabled",
                message="Exa collector is disabled.",
                details={
                    "planned_queries": 0,
                    "executed_queries": 0,
                    "failed_queries": 0,
                },
            )
        if not settings.exa_api_key:
            return [], ExaCollectionStatus(
                status="missing_config",
                message="Exa collection is enabled but EXA_API_KEY is not configured.",
                details={
                    "planned_queries": 0,
                    "executed_queries": 0,
                    "failed_queries": 0,
                },
            )

        plans = self._build_queries(request)
        if not plans:
            return [], ExaCollectionStatus(
                status="no_data",
                message="No Exa query plans were generated for this request.",
                details={
                    "planned_queries": 0,
                    "executed_queries": 0,
                    "failed_queries": 0,
                },
            )

        semaphore = asyncio.Semaphore(max(settings.exa_max_concurrency, 1))
        payloads: list[dict[str, Any]] = []
        failures = 0

        async def run_plan(plan: ExaQueryPlan) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await self._search_single_plan(request, plan)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Exa query failed",
                        extra={
                            "collector": self.source,
                            "target": request.target.name,
                            "query_family": plan.family,
                            "category": plan.category,
                            "query": plan.query,
                            "error": str(exc),
                        },
                    )
                    return None

        responses = await asyncio.gather(*(run_plan(plan) for plan in plans))
        for response in responses:
            if response is None:
                failures += 1
                continue
            payloads.append(response)

        if not payloads:
            status = ExaCollectionStatus(
                status="upstream_error",
                message="Exa collection failed for all planned queries.",
                details={
                    "planned_queries": len(plans),
                    "executed_queries": 0,
                    "failed_queries": failures,
                },
            )
            logger.warning(
                "Exa collection failed",
                extra={
                    "collector": self.source,
                    "target": request.target.name,
                    **status.details,
                },
            )
            return [], status

        total_results = sum(len(self._extract_results(payload)) for payload in payloads)
        status = ExaCollectionStatus(
            status="ok" if total_results > 0 else "no_data",
            message=(
                "Exa collection completed successfully."
                if total_results > 0
                else "Exa collection completed but returned no qualifying results."
            ),
            details={
                "planned_queries": len(plans),
                "executed_queries": len(payloads),
                "failed_queries": failures,
                "raw_results": total_results,
            },
        )
        logger.info(
            "Exa collection summary",
            extra={
                "collector": self.source,
                "target": request.target.name,
                **status.details,
            },
        )
        return payloads, status

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        payloads, status = await self._collect_payloads(request)
        if status.status != "ok":
            return self._build_findings(request, [], [], status), []

        request_ids = [
            request_id
            for request_id in (payload.get("requestId") for payload in payloads)
            if isinstance(request_id, str)
        ]
        normalized_results = self._normalize_results(request, payloads)
        if not normalized_results:
            no_data_status = ExaCollectionStatus(
                status="no_data",
                message="Exa collection completed but no results met the relevance threshold.",
                details={
                    **status.details,
                    "deduped_results": 0,
                    "qualified_results": 0,
                },
            )
            logger.info(
                "Exa collection produced no qualified results",
                extra={
                    "collector": self.source,
                    "target": request.target.name,
                    **no_data_status.details,
                },
            )
            return self._build_findings(request, request_ids, [], no_data_status), []

        enriched_status = ExaCollectionStatus(
            status=status.status,
            message=status.message,
            details={
                **status.details,
                "deduped_results": len(
                    {
                        item.document_id or item.canonical_url or item.title
                        for item in normalized_results
                    }
                ),
                "qualified_results": len(normalized_results),
            },
        )
        findings = self._build_findings(
            request, request_ids, normalized_results, enriched_status
        )
        logger.info(
            "Exa findings built",
            extra={
                "collector": self.source,
                "target": request.target.name,
                "finding_count": len(findings),
                **enriched_status.details,
            },
        )
        return findings, []
