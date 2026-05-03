"""CLI: run the Strava analyzer against a directory of real cached tiles
and write the result to `backend/ai/cached_results/<slug>_strava.json` so
`pipeline.run_full_assessment` can use it as deterministic demo fallback.

Member B: as soon as you have real Strava tiles for a location cached to
disk, run this once per location:

    python -m backend.ai.cache_real_data \\
        --tile-dir backend/data/cached/strava_tiles/fort_liberty \\
        --location "Fort Liberty, NC" \\
        --lat 35.1392 --lon -79.0060

The output JSON drops directly into the pipeline's cached_results/ slot
and gets picked up automatically — no other code changes needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import CACHE_DIR, slugify
from .strava_analyzer import analyze_strava_tiles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.ai.cache_real_data",
        description="Run the Strava analyzer on real tiles and cache the result.",
    )
    parser.add_argument(
        "--tile-dir",
        required=True,
        type=Path,
        help="Directory of cached Strava heatmap PNG tiles (slippy {z}/{x}/{y}.png recommended).",
    )
    parser.add_argument(
        "--location",
        required=True,
        help='Location name, e.g. "Fort Liberty, NC". Used as the cache filename slug.',
    )
    parser.add_argument("--lat", required=True, type=float)
    parser.add_argument("--lon", required=True, type=float)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=CACHE_DIR,
        help="Override the cached_results/ destination (default: backend/ai/cached_results).",
    )
    args = parser.parse_args(argv)

    if not args.tile_dir.exists():
        print(f"error: tile directory not found: {args.tile_dir}", file=sys.stderr)
        return 2

    print(f"Analyzing tiles in {args.tile_dir} ...")
    result = analyze_strava_tiles(args.tile_dir, args.lat, args.lon)
    print(json.dumps(result, indent=2))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{slugify(args.location)}_strava.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"\n✓ wrote {out_path}")
    print(
        f"  pipeline.run_full_assessment({args.location!r}, ...) will now "
        "use this as the strava fallback when no live tile dir is passed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
