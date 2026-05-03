"""
backend/ai/osint_sources.py
GHOSTLINE OSINT source collectors.

Provides synchronous collector functions that pull from real, public, attributable
sources and write raw responses to a cache directory for audit replay.

Every collector:
  - Returns a stable normalized dict (or None / [] on failure).
  - Never raises — errors are logged as warnings and the function returns a
    safe empty value so the orchestrator can keep running.
  - Writes the raw response to cache_dir as JSON (write-only, no cache reads).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_USER_AGENT = "GHOSTLINE-OPSEC/1.0 (abhiramyadu.sri@gmail.com)"

# Module-level session with default User-Agent.
_session = requests.Session()
_session.headers.update({"User-Agent": _USER_AGENT})

# Rate-limit state for Nominatim (1 req / sec).
_last_nominatim_call: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(s: str) -> str:
    """Return a filesystem-safe slug from *s*.

    Lowercase, ASCII-only (drop non-ASCII), spaces and punctuation → hyphens,
    collapse runs of hyphens, strip leading/trailing hyphens.  Max 80 chars.
    Empty input → "_".
    """
    if not s:
        return "_"
    # Normalise unicode then encode to ASCII, dropping non-ASCII chars.
    normalised = unicodedata.normalize("NFKD", s)
    ascii_str = normalised.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_str.lower()
    # Replace any character that is not alphanumeric with a hyphen.
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    # Collapse multiple hyphens, strip leading/trailing.
    collapsed = hyphenated.strip("-")
    if not collapsed:
        return "_"
    return collapsed[:80]


def with_retries(
    fn,
    retries: int = 3,
    base_delay: float = 1.0,
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
):
    """Call *fn()* which returns a :class:`requests.Response`.

    Retries on :exc:`requests.RequestException` and on response status codes
    listed in *retry_statuses*.  Uses exponential backoff (base_delay, 2×,
    4×, …).  Raises the last exception on exhaustion, or returns the final
    response if it has a non-retry status (even if non-2xx) — the caller
    must handle that case.
    """
    last_exc: Optional[Exception] = None
    delay = base_delay
    for attempt in range(retries):
        try:
            response = fn()
            if response.status_code not in retry_statuses:
                return response
            logger.warning(
                "with_retries: status %d on attempt %d/%d, retrying in %.1fs",
                response.status_code,
                attempt + 1,
                retries,
                delay,
            )
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "with_retries: %s on attempt %d/%d, retrying in %.1fs",
                exc,
                attempt + 1,
                retries,
                delay,
            )
        time.sleep(delay)
        delay *= 2

    # Final attempt (no more retries after this).
    try:
        return fn()
    except requests.RequestException as exc:
        raise exc
    # If we get here the last attempt returned a retry-status response;
    # re-raise the last stored exception if any, else return that response.
    if last_exc is not None:
        raise last_exc


# ---------------------------------------------------------------------------
# Internal cache helper
# ---------------------------------------------------------------------------


def _write_cache(cache_dir: Path, filename: str, data: object) -> None:
    """Atomically write *data* as JSON to *cache_dir/filename*."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_dir / (filename + ".tmp")
    dest_path = cache_dir / filename
    try:
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp_path), str(dest_path))
    except OSError as exc:
        logger.warning("Cache write failed for %s: %s", dest_path, exc)


# ---------------------------------------------------------------------------
# Collector 1 — Nominatim geocoding
# ---------------------------------------------------------------------------


def geocode_nominatim(query: str, cache_dir: Path) -> Optional[dict]:
    """Geocode *query* using the OSM Nominatim API.

    Respects Nominatim's 1 req/sec rate limit globally via a module-level
    timestamp.  Returns a normalised dict or None on empty result / error.
    """
    global _last_nominatim_call  # noqa: PLW0603

    # Enforce 1 req/sec rate limit.
    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)

    api_url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={quote(query)}&format=json&limit=1"
    )

    try:
        def _call() -> requests.Response:
            return _session.get(api_url, timeout=10)

        _last_nominatim_call = time.monotonic()
        response = with_retries(_call)
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("geocode_nominatim failed for %r: %s", query, exc)
        return None

    slug = slugify(query)
    _write_cache(cache_dir, f"nominatim__{slug}.json", raw)

    if not raw:
        return None

    hit = raw[0]
    try:
        return {
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
            "display_name": str(hit.get("display_name", "")),
            "osm_id": int(hit.get("osm_id", 0)),
            "osm_type": str(hit.get("osm_type", "")),
            "source_url": api_url,
        }
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("geocode_nominatim: could not parse result for %r: %s", query, exc)
        return None


# ---------------------------------------------------------------------------
# Collector 2 — Wikipedia REST summary
# ---------------------------------------------------------------------------


def wikipedia_summary(title: str, cache_dir: Path) -> Optional[dict]:
    """Fetch the Wikipedia summary paragraph for *title*.

    Returns None on 404 or any error.
    """
    encoded_title = quote(title, safe="")
    api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

    try:
        def _call() -> requests.Response:
            return _session.get(api_url, timeout=10)

        response = with_retries(_call)
        if response.status_code == 404:
            logger.warning("wikipedia_summary: 404 for %r", title)
            slug = slugify(title)
            _write_cache(cache_dir, f"wiki_summary__{slug}.json", {"error": "404", "title": title})
            return None
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("wikipedia_summary failed for %r: %s", title, exc)
        return None

    slug = slugify(title)
    _write_cache(cache_dir, f"wiki_summary__{slug}.json", raw)

    try:
        content_url = (
            raw.get("content_urls", {}).get("desktop", {}).get("page", "")
        )
        return {
            "title": str(raw.get("title", title)),
            "extract": str(raw.get("extract", "")),
            "content_url": str(content_url),
            "wikibase_item": raw.get("wikibase_item") or None,
            "source_url": api_url,
        }
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("wikipedia_summary: could not parse result for %r: %s", title, exc)
        return None


# ---------------------------------------------------------------------------
# Collector 3 — Wikipedia MediaWiki API parse (wikitext)
# ---------------------------------------------------------------------------


def wikipedia_parse(title: str, cache_dir: Path) -> Optional[dict]:
    """Fetch the raw wikitext for *title* via the MediaWiki Action API.

    Returns None if the page is missing (response has an ``error`` key) or
    on any error.
    """
    api_url = (
        "https://en.wikipedia.org/w/api.php"
        f"?action=parse&page={quote(title, safe='')}&format=json&prop=wikitext"
    )

    try:
        def _call() -> requests.Response:
            return _session.get(api_url, timeout=10)

        response = with_retries(_call)
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("wikipedia_parse failed for %r: %s", title, exc)
        return None

    slug = slugify(title)
    _write_cache(cache_dir, f"wiki_parse__{slug}.json", raw)

    if "error" in raw:
        logger.warning(
            "wikipedia_parse: API error for %r: %s",
            title,
            raw["error"].get("info", raw["error"]),
        )
        return None

    try:
        parse = raw["parse"]
        wikitext = parse["wikitext"]["*"]
        title_clean = str(parse.get("title", title))
        page_url = "https://en.wikipedia.org/wiki/" + quote(
            title_clean.replace(" ", "_"), safe=":"
        )
        return {
            "title": title_clean,
            "wikitext": str(wikitext),
            "page_url": page_url,
            "source_url": api_url,
        }
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("wikipedia_parse: could not parse result for %r: %s", title, exc)
        return None


# ---------------------------------------------------------------------------
# Collector 4 — Wikidata SPARQL
# ---------------------------------------------------------------------------


def wikidata_sparql(
    query: str,
    cache_dir: Path,
    name: str = "query",
) -> Optional[list[dict]]:
    """Execute a SPARQL query against Wikidata and return the bindings list.

    Posts to the Wikidata SPARQL endpoint.  Returns the raw
    ``results.bindings`` list or None on error.
    """
    endpoint = "https://query.wikidata.org/sparql"
    body = urlencode({"query": query})

    try:
        def _call() -> requests.Response:
            return _session.post(
                endpoint,
                data=body,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": _USER_AGENT,
                },
                timeout=30,
            )

        response = with_retries(_call)
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("wikidata_sparql failed for name=%r: %s", name, exc)
        return None

    slug = slugify(name)
    _write_cache(cache_dir, f"wikidata__{slug}.json", raw)

    try:
        bindings = raw["results"]["bindings"]
        return list(bindings)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("wikidata_sparql: could not parse bindings for name=%r: %s", name, exc)
        return None


# ---------------------------------------------------------------------------
# Collector 5 — Exa semantic search
# ---------------------------------------------------------------------------


def exa_search(
    query: str,
    cache_dir: Path,
    num_results: int = 5,
) -> list[dict]:
    """Search Exa.ai for *query* and return a list of normalised result dicts.

    Reads ``EXA_API_KEY`` from the environment (loaded via ``load_dotenv()``).
    Returns an empty list if the key is missing, or on any error.
    """
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        logger.warning("exa_search: EXA_API_KEY is not set — skipping")
        return []

    api_url = "https://api.exa.ai/search"
    payload = {
        "query": query,
        "numResults": num_results,
        "type": "neural",
        "useAutoprompt": True,
        "contents": {"text": True},
    }

    try:
        def _call() -> requests.Response:
            return _session.post(
                api_url,
                json=payload,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )

        response = with_retries(_call)
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("exa_search failed for %r: %s", query, exc)
        return []

    slug = slugify(query)
    _write_cache(cache_dir, f"exa__{slug}.json", raw)

    results = raw.get("results", [])
    if not isinstance(results, list):
        logger.warning("exa_search: unexpected response shape for %r", query)
        return []

    normalised = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalised.append(
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "text": str(item.get("text") or ""),
                "score": float(item.get("score") or 0.0),
            }
        )
    return normalised


# ---------------------------------------------------------------------------
# Collector 6 — Overpass QL
# ---------------------------------------------------------------------------


def overpass_query(
    query: str,
    cache_dir: Path,
    name: str = "overpass",
) -> Optional[dict]:
    """Execute an Overpass QL *query* and return the parsed JSON response.

    Adds ``_source_url`` to the returned dict.  Returns None on error.
    """
    endpoint = "https://overpass-api.de/api/interpreter"
    body = urlencode({"data": query})

    try:
        def _call() -> requests.Response:
            return _session.post(
                endpoint,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )

        response = with_retries(_call)
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("overpass_query failed for name=%r: %s", name, exc)
        return None

    slug = slugify(name)
    _write_cache(cache_dir, f"overpass__{slug}.json", raw)

    if not isinstance(raw, dict):
        logger.warning("overpass_query: unexpected response type for name=%r", name)
        return None

    raw["_source_url"] = endpoint
    return raw


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    cache_dir = Path("/tmp/ghostline_test_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1. Nominatim
    print("\n--- geocode_nominatim('Fort Liberty, NC') ---")
    geo = geocode_nominatim("Fort Liberty, NC", cache_dir)
    if geo:
        print(f"  SUCCESS  lat={geo['lat']}  lon={geo['lon']}")
    else:
        print("  RESULT: None")

    # 2. Wikipedia summary
    print("\n--- wikipedia_summary('Fort_Bragg') ---")
    summary = wikipedia_summary("Fort_Bragg", cache_dir)
    if summary:
        print(f"  SUCCESS  extract length={len(summary['extract'])}")
    else:
        print("  RESULT: None")

    # 3. Wikipedia parse
    print("\n--- wikipedia_parse('Fort_Bragg') ---")
    parsed = wikipedia_parse("Fort_Bragg", cache_dir)
    if parsed:
        print(f"  SUCCESS  wikitext length={len(parsed['wikitext'])}")
    else:
        print("  RESULT: None")

    # 4. Exa search (skip cleanly if no key)
    print("\n--- exa_search('units stationed at Fort Liberty', num_results=3) ---")
    if not os.getenv("EXA_API_KEY"):
        print("  SKIPPED  (EXA_API_KEY not set)")
    else:
        results = exa_search("units stationed at Fort Liberty", cache_dir, num_results=3)
        print(f"  SUCCESS  result count={len(results)}")

    # List cache files
    print("\n--- Cache files written ---")
    for p in sorted(cache_dir.iterdir()):
        print(f"  {p.name}")
