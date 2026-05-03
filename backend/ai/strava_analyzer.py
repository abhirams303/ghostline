"""Pixel-level analysis of Strava heatmap PNG tiles.

Reads cached Strava heatmap tiles from disk and infers an exposure score
plus the cardinal-direction quadrant where activity is concentrated.
Strava heatmap tiles encode activity intensity in pixel brightness — black
means none, brighter means more — so basic image stats give us a usable
density and intensity signal without an API key.
"""

from __future__ import annotations

import collections
import logging
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

_ACTIVE_BRIGHTNESS_THRESHOLD = 30
_MAX_TILES = 256
_MIN_COMPONENT_SIZE = 12
# NOTE: Strava heatmap PNG tiles carry no temporal data — these are the
# typical PT-cycle hours, not observed peaks. Real time-of-day inference
# would require the authenticated Strava activity API.
_PEAK_HOURS_DEFAULT = ["0600-0700", "1700-1800"]
_QUADRANT_LABEL = {
    "NE": "eastern perimeter",
    "NW": "northern sector",
    "SE": "southern sector",
    "SW": "western perimeter",
}

_SLIPPY_RE = re.compile(r"(?:^|/)(\d{1,2})/(\d+)/(\d+)(?:@\dx)?\.png$")
_FLAT_RE = re.compile(r"(\d{1,2})[-_](\d+)[-_](\d+)(?:@\dx)?\.png$")


def _zero_strava_result(note: str) -> dict:
    return {
        "density_score": 0,
        "route_count": 0,
        "peak_hours": list(_PEAK_HOURS_DEFAULT),
        "hotspots": [],
        "raw_metrics": {
            "tiles_analyzed": 0,
            "total_pixels": 0,
            "active_pixels": 0,
            "avg_brightness": 0.0,
            "density_ratio": 0.0,
            "layout": "empty",
        },
        "note": note,
    }


def _collect_png_paths(tile_dir: Path) -> list[Path]:
    if not tile_dir.exists() or not tile_dir.is_dir():
        return []
    paths = sorted(tile_dir.rglob("*.png"))
    if len(paths) > _MAX_TILES:
        log.warning(
            "strava_analyzer: %d tiles found, truncating to %d",
            len(paths),
            _MAX_TILES,
        )
        paths = paths[:_MAX_TILES]
    return paths


def _parse_tile_xyz(path: Path) -> tuple[int, int, int] | None:
    s = path.as_posix()
    for rx in (_SLIPPY_RE, _FLAT_RE):
        m = rx.search(s)
        if m:
            z, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 0 <= z <= 22:
                return z, x, y
    return None


def _tile_xyz_to_latlon(z: int, x: int, y: int) -> tuple[float, float]:
    n = 2 ** z
    tile_lon = (x + 0.5) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n)))
    return math.degrees(lat_rad), tile_lon


def _quadrant_for(
    tile_lat: float,
    tile_lon: float,
    c_lat: float,
    c_lon: float,
) -> str:
    north = tile_lat >= c_lat
    east = tile_lon >= c_lon
    if north and east:
        return "NE"
    if north and not east:
        return "NW"
    if not north and east:
        return "SE"
    return "SW"


def _count_components(mask: np.ndarray, min_size: int) -> int:
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    count = 0
    for y0 in range(h):
        row_mask = mask[y0]
        for x0 in range(w):
            if not row_mask[x0] or visited[y0, x0]:
                continue
            queue = collections.deque()
            queue.append((y0, x0))
            visited[y0, x0] = True
            size = 0
            while queue:
                y, x = queue.popleft()
                size += 1
                if y > 0 and mask[y - 1, x] and not visited[y - 1, x]:
                    visited[y - 1, x] = True
                    queue.append((y - 1, x))
                if y + 1 < h and mask[y + 1, x] and not visited[y + 1, x]:
                    visited[y + 1, x] = True
                    queue.append((y + 1, x))
                if x > 0 and mask[y, x - 1] and not visited[y, x - 1]:
                    visited[y, x - 1] = True
                    queue.append((y, x - 1))
                if x + 1 < w and mask[y, x + 1] and not visited[y, x + 1]:
                    visited[y, x + 1] = True
                    queue.append((y, x + 1))
            if size >= min_size:
                count += 1
    return count


def analyze_strava_tiles(
    tile_dir: str | Path,
    center_lat: float,
    center_lon: float,
) -> dict:
    """Compute density, intensity, hotspot quadrant, and route count.

    Args:
        tile_dir: directory of cached Strava PNG tiles. Recursively globbed;
            slippy `{z}/{x}/{y}.png` paths are recognized for spatial analysis,
            other layouts degrade gracefully to non-spatial aggregation.
        center_lat, center_lon: target location used to assign each tile to
            an NE/NW/SE/SW quadrant.
    """
    tile_dir = Path(tile_dir)
    paths = _collect_png_paths(tile_dir)
    if not paths:
        return _zero_strava_result(f"no tiles found in {tile_dir}")

    total_pixels = 0
    active_pixels = 0
    sum_active_brightness = 0.0
    route_count = 0
    quadrant_brightness: dict[str, float] = {"NE": 0.0, "NW": 0.0, "SE": 0.0, "SW": 0.0}
    parsed_count = 0
    loaded_count = 0

    for path in paths:
        try:
            with Image.open(path) as im:
                arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
        except Exception as exc:  # noqa: BLE001 — corrupt PNG must not crash demo
            log.warning("strava_analyzer: skipping unreadable tile %s (%s)", path, exc)
            continue

        loaded_count += 1
        h, w, _ = arr.shape
        brightness = arr.mean(axis=2)
        mask = brightness >= _ACTIVE_BRIGHTNESS_THRESHOLD
        tile_active = int(mask.sum())
        total_pixels += h * w
        active_pixels += tile_active
        if tile_active:
            tile_active_brightness_sum = float(brightness[mask].sum())
            sum_active_brightness += tile_active_brightness_sum
        else:
            tile_active_brightness_sum = 0.0

        route_count += _count_components(mask, _MIN_COMPONENT_SIZE)

        xyz = _parse_tile_xyz(path)
        if xyz is not None:
            parsed_count += 1
            tile_lat, tile_lon = _tile_xyz_to_latlon(*xyz)
            q = _quadrant_for(tile_lat, tile_lon, center_lat, center_lon)
            quadrant_brightness[q] += tile_active_brightness_sum

    if loaded_count == 0:
        return _zero_strava_result("all tiles failed to load")

    density_ratio = active_pixels / total_pixels if total_pixels else 0.0
    density_ratio_norm = min(100.0, density_ratio * 100.0 * 50.0)
    avg_brightness = (
        sum_active_brightness / active_pixels if active_pixels else 0.0
    )
    intensity_norm = (avg_brightness / 255.0) * 100.0
    density_score = max(
        0,
        min(100, round(0.6 * density_ratio_norm + 0.4 * intensity_norm)),
    )

    if parsed_count >= 0.5 * loaded_count:
        layout = "slippy"
        max_q = max(quadrant_brightness, key=lambda k: quadrant_brightness[k])
        hotspots = (
            [_QUADRANT_LABEL[max_q]] if quadrant_brightness[max_q] > 0 else []
        )
    else:
        layout = "non-spatial"
        hotspots = []

    return {
        "density_score": density_score,
        "route_count": route_count,
        "peak_hours": list(_PEAK_HOURS_DEFAULT),
        "hotspots": hotspots,
        "raw_metrics": {
            "tiles_analyzed": loaded_count,
            "total_pixels": total_pixels,
            "active_pixels": active_pixels,
            "avg_brightness": round(avg_brightness, 1),
            "density_ratio": round(density_ratio, 4),
            "layout": layout,
        },
        "note": None,
    }
