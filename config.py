from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    internal_api_key: str
    route_calculator_url: str | None
    route_calculator_key: str
    route_calculator_path: str
    environment: str
    host: str
    port: int
    default_search_radius_km: float
    default_max_candidates: int
    max_location_staleness_seconds: int
    max_vehicle_location_staleness_seconds: int
    route_calculator_top_n: int
    local_database_path: Path


def load_settings(base_dir: Path | None = None) -> Settings:
    root = base_dir or Path(__file__).resolve().parent
    return Settings(
        database_url=os.getenv("DATABASE_URL", "").strip() or None,
        internal_api_key=os.getenv("INTERNAL_API_KEY", "dev-internal-key").strip(),
        route_calculator_url=os.getenv("ROUTE_CALCULATOR_URL", "").strip() or None,
        route_calculator_key=os.getenv("ROUTE_CALCULATOR_KEY", "").strip(),
        route_calculator_path=os.getenv("ROUTE_CALCULATOR_PATH", "/route/calculate").strip() or "/route/calculate",
        environment=os.getenv("ENVIRONMENT", "production").strip(),
        host=os.getenv("HOST", "0.0.0.0").strip(),
        port=int(os.getenv("PORT", "8000")),
        default_search_radius_km=float(os.getenv("DEFAULT_SEARCH_RADIUS_KM", "5")),
        default_max_candidates=int(os.getenv("DEFAULT_MAX_CANDIDATES", "10")),
        max_location_staleness_seconds=int(os.getenv("MAX_LOCATION_STALENESS_SECONDS", "300")),
        max_vehicle_location_staleness_seconds=int(os.getenv("MAX_VEHICLE_LOCATION_STALENESS_SECONDS", "600")),
        route_calculator_top_n=int(os.getenv("ROUTE_CALCULATOR_TOP_N", "8")),
        local_database_path=Path(os.getenv("LOCAL_DATABASE_PATH", root / "proximity.db")),
    )
