"""Fetch one Strava heatmap tile and save it for visual verification.

Run from backend/:
    python scripts/smoke_strava.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import httpx
import mercantile
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors.strava import HEADERS, TILE_URL, _cookies


async def main() -> None:
    load_dotenv()

    lat, lon, zoom = 37.7749, -122.4194, 13
    tile = mercantile.tile(lon, lat, zoom)
    url = TILE_URL.format(activity="all", color="blue", z=zoom, x=tile.x, y=tile.y)

    print(f"GET {url}")
    async with httpx.AsyncClient(cookies=_cookies(), headers=HEADERS, timeout=15) as client:
        response = await client.get(url)

    print(f"Status: {response.status_code}  Bytes: {len(response.content)}")
    if response.status_code != 200:
        print(f"FAIL body: {response.text[:300]}")
        return
    if len(response.content) < 500:
        print("WARNING: tiny PNG means empty tile. Try a denser coordinate.")
        return

    output_path = Path("test_tile.png")
    output_path.write_bytes(response.content)
    print(f"Saved {output_path} - open it and confirm the heatmap glow is visible.")


if __name__ == "__main__":
    asyncio.run(main())
