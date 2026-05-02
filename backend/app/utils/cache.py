import json
from pathlib import Path

from app.models.report import AnalyzeResponse
from app.utils.geo import slugify_location


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "cached"


def load_cached_report(location_name: str) -> AnalyzeResponse | None:
    file_path = DATA_DIR / f"{slugify_location(location_name)}.json"
    if not file_path.exists():
        return None

    payload = json.loads(file_path.read_text(encoding="utf-8"))
    return AnalyzeResponse.model_validate(payload)
