from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from app.models.finding import Finding
from app.models.location import AnalyzeRequest
from app.models.report import AnalyzeResponse


SCHEMA = """
CREATE TABLE IF NOT EXISTS search_runs (
    run_id TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    mode TEXT NOT NULL,
    target_name TEXT NOT NULL,
    target_lat REAL NOT NULL,
    target_lon REAL NOT NULL,
    radius_km REAL NOT NULL,
    route_json TEXT NOT NULL,
    unit_id TEXT,
    generated_at TEXT NOT NULL,
    score_json TEXT NOT NULL,
    narrative_preview TEXT NOT NULL,
    response_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_search_runs_request_fingerprint
    ON search_runs (request_fingerprint);

CREATE TABLE IF NOT EXISTS source_documents (
    document_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT,
    canonical_url TEXT,
    title TEXT NOT NULL,
    published_at TEXT,
    content_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_documents_source
    ON source_documents (source);

CREATE TABLE IF NOT EXISTS run_documents (
    run_id TEXT NOT NULL,
    document_key TEXT NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (run_id, document_key),
    FOREIGN KEY (run_id) REFERENCES search_runs(run_id),
    FOREIGN KEY (document_key) REFERENCES source_documents(document_key)
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_url TEXT,
    geo_lat REAL,
    geo_lon REAL,
    ts TEXT,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES search_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_findings_run_id
    ON findings (run_id);
"""


def initialize_storage(database_path: Path) -> None:
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def persist_analysis_run(
    database_path: Path,
    request: AnalyzeRequest,
    response: AnalyzeResponse,
) -> None:
    request_payload = request.model_dump(mode="json")
    response_payload = response.model_dump(mode="json")
    request_fingerprint = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    generated_at = response.generated_at.isoformat()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT OR REPLACE INTO search_runs (
                run_id,
                request_fingerprint,
                mode,
                target_name,
                target_lat,
                target_lon,
                radius_km,
                route_json,
                unit_id,
                generated_at,
                score_json,
                narrative_preview,
                response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                response.run_id,
                request_fingerprint,
                response.mode,
                response.target.name,
                response.target.lat,
                response.target.lon,
                response.target.radius_km,
                json.dumps(request_payload["route"], sort_keys=True),
                request.unit_id,
                generated_at,
                json.dumps(response_payload["score"], sort_keys=True),
                response.narrative_preview,
                json.dumps(response_payload, sort_keys=True),
            ),
        )

        for rank, finding in enumerate(response.findings, start=1):
            _persist_finding(
                connection=connection,
                run_id=response.run_id,
                rank=rank,
                finding=finding,
                generated_at=generated_at,
            )

        connection.commit()


def _persist_finding(
    connection: sqlite3.Connection,
    run_id: str,
    rank: int,
    finding: Finding,
    generated_at: str,
) -> None:
    metadata_json = json.dumps(finding.metadata, sort_keys=True, default=str)
    source_document = _build_source_document(finding)

    connection.execute(
        """
        INSERT INTO source_documents (
            document_key,
            source,
            external_id,
            canonical_url,
            title,
            published_at,
            content_hash,
            first_seen_at,
            last_seen_at,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_key) DO UPDATE SET
            external_id = COALESCE(excluded.external_id, source_documents.external_id),
            canonical_url = COALESCE(excluded.canonical_url, source_documents.canonical_url),
            title = excluded.title,
            published_at = COALESCE(excluded.published_at, source_documents.published_at),
            content_hash = excluded.content_hash,
            last_seen_at = excluded.last_seen_at,
            raw_json = excluded.raw_json
        """,
        (
            source_document["document_key"],
            source_document["source"],
            source_document["external_id"],
            source_document["canonical_url"],
            source_document["title"],
            source_document["published_at"],
            source_document["content_hash"],
            generated_at,
            generated_at,
            json.dumps(source_document["raw_json"], sort_keys=True, default=str),
        ),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO run_documents (run_id, document_key, rank)
        VALUES (?, ?, ?)
        """,
        (run_id, source_document["document_key"], rank),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO findings (
            finding_id,
            run_id,
            source,
            title,
            severity,
            summary,
            evidence_url,
            geo_lat,
            geo_lon,
            ts,
            metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{run_id}:{rank}",
            run_id,
            finding.source,
            finding.title,
            finding.severity,
            finding.summary,
            finding.evidence_url,
            finding.geo.lat if finding.geo else None,
            finding.geo.lon if finding.geo else None,
            finding.ts.isoformat() if finding.ts else None,
            metadata_json,
        ),
    )


def _build_source_document(finding: Finding) -> dict[str, object]:
    metadata = finding.metadata
    canonical_url = metadata.get("canonical_url") or finding.evidence_url
    external_id = (
        metadata.get("source_document_id")
        or metadata.get("document_id")
        or metadata.get("external_id")
    )
    published_at = metadata.get("published_at")
    if not published_at and finding.ts:
        published_at = finding.ts.isoformat()

    document_seed = {
        "source": finding.source,
        "title": finding.title,
        "summary": finding.summary,
        "canonical_url": canonical_url,
        "external_id": external_id,
    }
    document_key = external_id or canonical_url or hashlib.sha256(
        json.dumps(document_seed, sort_keys=True).encode("utf-8")
    ).hexdigest()

    raw_json = {
        "title": finding.title,
        "summary": finding.summary,
        "evidence_url": finding.evidence_url,
        "metadata": metadata,
    }
    content_hash = hashlib.sha256(
        json.dumps(raw_json, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    return {
        "document_key": str(document_key),
        "source": finding.source,
        "external_id": external_id,
        "canonical_url": canonical_url,
        "title": metadata.get("document_title") or finding.title,
        "published_at": published_at,
        "content_hash": content_hash,
        "raw_json": raw_json,
    }
