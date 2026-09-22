# Proximity

Deterministic officer/vehicle proximity and fit-ranking engine for the Lemtik
Security C4I platform. Given an incident location and a pool of candidate
officers/vehicles, it returns a ranked shortlist of who should be dispatched.

No AI or LLM is used in this service by design — ranking is a pure,
explainable algorithm (Haversine pre-filter → optional Route Calculator ETA
on the top candidates → weighted fit score), which keeps responses fast
(target: under 600ms) and keeps the reasoning behind a dispatch
recommendation fully auditable.

## How ranking works

1. **Haversine pre-filter** — cheap straight-line distance narrows the full
   candidate pool down to the closest few before any network call is made.
2. **Route Calculator ETA** — for the top candidates, a real road-network ETA
   is requested from the Route Calculator service. If that service is slow or
   unavailable, proximity falls back to straight-line distance rather than
   blocking the response.
3. **Fit score** — candidates are ranked on distance/ETA, armed/certification
   match against the incident type, fatigue, and indoor/building match (an
   officer already inside the same building as an indoor incident is ranked
   above anyone GPS-closer but outside).

## Eligibility rules

- Only on-shift officers/vehicles are considered.
- An officer's location must be fresh within `MAX_LOCATION_STALENESS_SECONDS`
  (default 300s / 5 min); a vehicle's within
  `MAX_VEHICLE_LOCATION_STALENESS_SECONDS` (default 600s / 10 min). Stale
  locations are excluded rather than trusted.
- Officers/vehicles already dispatched to another active incident are
  excluded from ranking for a new one.
- Location data is not retained after an officer's shift ends.

## Endpoints

- `POST /find` — find and rank candidate officers/vehicles for an incident.
- `GET /health` — service and dependency health (database, Route Calculator
  reachability).
- `GET /queries` — recent query log for debugging/audit.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (falls back to local SQLite for demo/dev if unset) |
| `INTERNAL_API_KEY` | Shared-secret key required on internal service calls in production |
| `ROUTE_CALCULATOR_URL` | Base URL of the Route Calculator service |
| `ROUTE_CALCULATOR_KEY` | Internal key used when calling the Route Calculator |
| `ROUTE_CALCULATOR_PATH` | Path on the Route Calculator used for ETA lookups (default `/route/calculate`) |
| `ENVIRONMENT` | `production` or `development`; production requires `INTERNAL_API_KEY` to be set |
| `HOST` / `PORT` | Bind address (defaults `0.0.0.0:8000`) |
| `DEFAULT_SEARCH_RADIUS_KM` | Initial Haversine search radius (default 5km) |
| `DEFAULT_MAX_CANDIDATES` | Max candidates returned (default 10) |
| `MAX_LOCATION_STALENESS_SECONDS` | Officer location freshness window (default 300s) |
| `MAX_VEHICLE_LOCATION_STALENESS_SECONDS` | Vehicle location freshness window (default 600s) |
| `ROUTE_CALCULATOR_TOP_N` | How many top candidates get a real ETA lookup (default 8) |
| `LOCAL_DATABASE_PATH` | Path to the local SQLite fallback database |

## Running locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

## License

Proprietary — All Rights Reserved. See [LICENSE](./LICENSE). This code is
shared publicly for evaluation purposes only; it is not licensed for reuse,
modification, or redistribution.

---

© 2026 Lemtik Security. All rights reserved.
