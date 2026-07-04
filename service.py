from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:  # Optional dependency for deployment/runtime.
    import httpx
except Exception:  # pragma: no cover - optional import
    httpx = None  # type: ignore

from config import Settings
from storage import ProximityStore


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lng / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def metres_to_display(distance_metres: int) -> str:
    if distance_metres < 1000:
        return f"{distance_metres}m"
    km = distance_metres / 1000.0
    return f"{km:.1f}km"


def eta_display(seconds: int | None) -> str:
    if seconds is None:
        return "ETA unavailable"
    minutes, secs = divmod(max(0, int(round(seconds))), 60)
    if minutes <= 0:
        return f"{secs} sec"
    return f"{minutes} min {secs} sec"


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat)))
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta


def distance_score(distance_metres: int) -> float:
    if distance_metres <= 500:
        return 100.0
    if distance_metres <= 1000:
        return 90.0
    if distance_metres <= 2000:
        return 75.0
    if distance_metres <= 3000:
        return 60.0
    return 40.0


def fit_score(
    candidate: dict[str, Any],
    incident: dict[str, Any],
    distance_metres: int,
    eta_seconds: int | None,
    kind: str,
) -> tuple[float, dict[str, Any], str]:
    score = distance_score(distance_metres)
    details: dict[str, Any] = {
        "distance_score": round(score, 2),
        "armed_match": True,
        "certifications_matched": [],
        "certifications_missing": [],
        "fatigue_flag": False,
        "hours_on_shift": round(float(candidate.get("hours_on_shift") or 0.0), 2),
    }
    reason_bits: list[str] = []
    requirements = incident.get("requirements") or {}
    building = incident.get("location") or {}
    indoor = bool(building.get("indoor"))

    if kind == "officer":
        if requirements.get("armed_required") and not candidate.get("armed"):
            score -= 40
            details["armed_match"] = False
            reason_bits.append("armed requirement unmet")
        preferred = requirements.get("certifications_preferred") or []
        required = requirements.get("required_certifications") or []
        requested = list(dict.fromkeys([*required, *preferred]))
        certs = set(candidate.get("certifications") or [])
        matched = [cert for cert in requested if cert in certs]
        missing = [cert for cert in requested if cert not in certs]
        if requested:
            score += (len(matched) / len(requested)) * 15
        details["certifications_matched"] = matched
        details["certifications_missing"] = missing
        if float(candidate.get("hours_on_shift") or 0.0) > 10:
            score -= 15
            details["fatigue_flag"] = True
            reason_bits.append("fatigued")
        if indoor and candidate.get("current_building_id") and candidate.get("current_building_id") == building.get("building_id"):
            score += 15
            reason_bits.append("same building")
            if candidate.get("current_floor") is not None and building.get("floor") is not None:
                floor_gap = abs(int(candidate["current_floor"]) - int(building["floor"]))
                score += max(0, 6 - floor_gap * 2)
    else:
        vehicle_type_required = requirements.get("vehicle_type")
        if vehicle_type_required and candidate.get("type") != vehicle_type_required:
            score -= 30
            reason_bits.append("vehicle type mismatch")
        capacity_needed = int(requirements.get("officers_needed") or 0)
        if capacity_needed and int(candidate.get("capacity") or 0) < capacity_needed:
            score -= 12
            reason_bits.append("capacity limited")
        fuel = int(candidate.get("fuel_percentage") or 0)
        if fuel < 25:
            score -= 30
            reason_bits.append("fuel low")
        elif fuel < 40:
            score -= 10
        if not candidate.get("assigned_driver_id"):
            score -= 8
            reason_bits.append("driver unassigned")
        if float(candidate.get("hours_on_shift") or 0.0) > 10:
            score -= 10
            details["fatigue_flag"] = True

    if eta_seconds is not None and eta_seconds > 0:
        if eta_seconds <= 90:
            score += 8
        elif eta_seconds <= 300:
            score += 3
        elif eta_seconds > 900:
            score -= 5

    if indoor and candidate.get("current_building_id") == building.get("building_id"):
        score += 5

    final = max(0.0, min(100.0, score))
    if not reason_bits:
        reason_bits.append("closest fit")
    if kind == "officer":
        if candidate.get("armed"):
            reason_bits.insert(0, "armed")
        if details["certifications_matched"]:
            reason_bits.append(", ".join(details["certifications_matched"]))
    return final, details, ", ".join(reason_bits)


def format_seconds(seconds: int | None) -> int | None:
    if seconds is None:
        return None
    return int(round(seconds))


@dataclass
class ProximityResult:
    payload: dict[str, Any]
    route_calculator_called: bool
    candidates_sent_to_route_calculator: int


class ProximityService:
    def __init__(self, settings: Settings, store: ProximityStore):
        self.settings = settings
        self.store = store

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "proximity",
            "environment": self.settings.environment,
            "dependencies": {
                "database": self.store.health(),
                "route_calculator": bool(self.settings.route_calculator_url),
            },
            "timestamp": now_utc().isoformat(),
        }

    def _validate_internal_key(self, provided_key: str | None) -> None:
        if provided_key != self.settings.internal_api_key:
            raise PermissionError("invalid internal api key")

    def _stale_seconds(self, updated_at: Any) -> int | None:
        parsed = parse_iso(updated_at)
        if not parsed:
            return None
        return max(0, int((now_utc() - parsed).total_seconds()))

    def _base_officer_filter(self, officer: dict[str, Any], incident: dict[str, Any], assigned_ids: set[str]) -> tuple[bool, str | None]:
        if officer.get("status") not in {"available", "on_duty"}:
            return False, "not_on_shift"
        if not officer.get("shift_start"):
            return False, "not_on_shift"
        if officer.get("officer_id") in assigned_ids:
            return False, "already_responding"
        if officer.get("assigned_incident_id"):
            return False, "already_responding"
        if officer.get("current_lat") is None or officer.get("current_lng") is None:
            return False, "location_unknown"
        stale_seconds = self._stale_seconds(officer.get("location_updated_at"))
        if stale_seconds is None or stale_seconds > self.settings.max_location_staleness_seconds:
            return False, "location_stale"
        return True, None

    def _base_vehicle_filter(self, vehicle: dict[str, Any]) -> tuple[bool, str | None]:
        if vehicle.get("status") != "available":
            return False, "not_available"
        if vehicle.get("current_lat") is None or vehicle.get("current_lng") is None:
            return False, "location_unknown"
        stale_seconds = self._stale_seconds(vehicle.get("location_updated_at"))
        if stale_seconds is None or stale_seconds > self.settings.max_vehicle_location_staleness_seconds:
            return False, "location_stale"
        if int(vehicle.get("fuel_percentage") or 0) < 25:
            return False, "fuel_low"
        return True, None

    def _prepare_officer_candidate(self, officer: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
        location = incident.get("location") or {}
        current_lat = float(officer["current_lat"])
        current_lng = float(officer["current_lng"])
        distance = int(round(haversine_distance(current_lat, current_lng, float(location["lat"]), float(location["lng"]))))
        stale_seconds = self._stale_seconds(officer.get("location_updated_at")) or 0
        candidate = {
            "resource_type": "officer",
            "officer_id": officer.get("officer_id"),
            "name": officer.get("name"),
            "badge": officer.get("badge_number"),
            "contact": officer.get("contact"),
            "status": officer.get("status"),
            "armed": bool(officer.get("armed")),
            "weapon": officer.get("weapon_id"),
            "certifications": list(officer.get("certifications") or []),
            "current_location": {
                "lat": current_lat,
                "lng": current_lng,
                "description": officer.get("assigned_zone") or "unknown",
                "last_updated": officer.get("location_updated_at"),
                "seconds_since_update": stale_seconds,
            },
            "distance_metres": distance,
            "haversine_distance_metres": distance,
            "eta_seconds": None,
            "eta_display": "ETA not calculated",
            "route_type": "foot",
            "hours_on_shift": float(officer.get("hours_on_shift") or 0.0),
            "current_building_id": officer.get("current_building_id"),
            "current_floor": officer.get("current_floor"),
            "equipment_carried": list(officer.get("equipment_carried") or []),
            "source": officer,
        }
        return candidate

    def _prepare_vehicle_candidate(self, vehicle: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
        location = incident.get("location") or {}
        current_lat = float(vehicle["current_lat"])
        current_lng = float(vehicle["current_lng"])
        distance = int(round(haversine_distance(current_lat, current_lng, float(location["lat"]), float(location["lng"]))))
        stale_seconds = self._stale_seconds(vehicle.get("location_updated_at")) or 0
        candidate = {
            "resource_type": "vehicle",
            "vehicle_id": vehicle.get("vehicle_id"),
            "name": vehicle.get("plate_number") or vehicle.get("vehicle_id"),
            "badge": vehicle.get("plate_number"),
            "contact": None,
            "status": vehicle.get("status"),
            "armed": False,
            "weapon": None,
            "certifications": [],
            "current_location": {
                "lat": current_lat,
                "lng": current_lng,
                "description": vehicle.get("type") or "vehicle",
                "last_updated": vehicle.get("location_updated_at"),
                "seconds_since_update": stale_seconds,
            },
            "distance_metres": distance,
            "haversine_distance_metres": distance,
            "eta_seconds": None,
            "eta_display": "ETA not calculated",
            "route_type": "vehicle",
            "hours_on_shift": float(vehicle.get("hours_on_shift") or 0.0),
            "fuel_percentage": int(vehicle.get("fuel_percentage") or 0),
            "capacity": int(vehicle.get("capacity") or 0),
            "type": vehicle.get("type"),
            "assigned_driver_id": vehicle.get("assigned_driver_id"),
            "special_equipment": list(vehicle.get("special_equipment") or []),
            "source": vehicle,
        }
        return candidate

    def _same_building_boost(self, candidate: dict[str, Any], incident: dict[str, Any]) -> bool:
        location = incident.get("location") or {}
        if not location.get("indoor"):
            return False
        building_id = location.get("building_id")
        return bool(building_id and candidate.get("current_building_id") == building_id)

    def _short_reason(self, candidate: dict[str, Any], breakdown: dict[str, Any], eta_seconds: int | None, incident: dict[str, Any]) -> str:
        pieces: list[str] = []
        if self._same_building_boost(candidate, incident):
            pieces.append("same building")
        if candidate.get("resource_type") == "officer":
            if candidate.get("armed"):
                pieces.append("armed")
            if breakdown.get("certifications_matched"):
                pieces.append(", ".join(breakdown["certifications_matched"]))
        elif candidate.get("fuel_percentage") is not None:
            pieces.append(f"{int(candidate['fuel_percentage'])}% fuel")
        if eta_seconds is not None:
            pieces.append(f"{eta_display(eta_seconds)} ETA")
        return ", ".join(pieces) or "closest fit"

    async def _route_calculator_etAs(self, payload: dict[str, Any], candidates: list[dict[str, Any]], incident: dict[str, Any]) -> tuple[bool, int, list[dict[str, Any]]]:
        if not self.settings.route_calculator_url or httpx is None:
            return False, 0, candidates
        top_n = max(1, self.settings.route_calculator_top_n)
        to_route = candidates[:top_n]
        responders = []
        officer_ids: list[str] = []
        for candidate in to_route:
            responder_id = candidate.get("officer_id") or candidate.get("vehicle_id")
            if not responder_id:
                continue
            if candidate["resource_type"] == "officer":
                officer_ids.append(responder_id)
            responders.append(
                {
                    "id": responder_id,
                    "type": "vehicle" if candidate["resource_type"] == "vehicle" else "officer_foot",
                    "current_location": {
                        "lat": candidate["current_location"]["lat"],
                        "lng": candidate["current_location"]["lng"],
                    },
                }
            )
        if not responders:
            return False, 0, candidates
        request_payload = {
            "request_id": f'{payload["request_id"]}_eta',
            "request_type": "route_calculate",
            "org_id": payload["org_id"],
            "incident": {
                "id": incident.get("id"),
                "location": incident.get("location"),
                "indoor": bool((incident.get("location") or {}).get("indoor")),
            },
            "responders": {
                "officers": officer_ids,
                "vehicles": [candidate["vehicle_id"] for candidate in to_route if candidate["resource_type"] == "vehicle"],
            },
            "routing_preferences": {"prioritise": "speed", "type": "foot"},
        }
        timeout = httpx.Timeout(8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.settings.route_calculator_url.rstrip('/')}{self.settings.route_calculator_path}",
                json=request_payload,
                headers={"X-Internal-Key": self.settings.route_calculator_key} if self.settings.route_calculator_key else {},
            )
        response.raise_for_status()
        body = response.json()
        routes = (((body or {}).get("data") or {}).get("routes")) or []
        route_map: dict[str, dict[str, Any]] = {}
        for route in routes:
            officer_id = route.get("officer_id")
            vehicle_id = route.get("vehicle_id")
            if officer_id:
                route_map[officer_id] = route
            if vehicle_id:
                route_map[vehicle_id] = route
        for candidate in to_route:
            key = candidate.get("officer_id") or candidate.get("vehicle_id")
            route = route_map.get(key, {})
            eta_minutes = route.get("estimated_time_minutes")
            eta_seconds = route.get("estimated_time_seconds")
            if eta_seconds is None and eta_minutes is not None:
                eta_seconds = int(round(float(eta_minutes) * 60))
            distance_metres = route.get("distance_metres") or candidate["distance_metres"]
            candidate["eta_seconds"] = format_seconds(eta_seconds) if eta_seconds is not None else None
            candidate["eta_display"] = route.get("estimated_time_display") or eta_display(candidate["eta_seconds"])
            candidate["distance_metres"] = int(distance_metres)
            candidate["route_type"] = route.get("type") or candidate["route_type"]
        return True, len(to_route), candidates

    def _build_recommendation(self, candidate: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
        source = candidate["source"]
        distance_metres = int(candidate["distance_metres"])
        eta_seconds = candidate.get("eta_seconds")
        score, breakdown, reason_bits = fit_score(source, incident, distance_metres, eta_seconds, candidate["resource_type"])
        candidate["fit_score"] = round(score, 2)
        candidate["fit_breakdown"] = breakdown
        candidate["recommendation_reason"] = self._short_reason(candidate, breakdown, eta_seconds, incident)
        item = {
            "status": candidate.get("status"),
            "armed": candidate.get("armed"),
            "weapon": candidate.get("weapon"),
            "certifications": candidate.get("certifications"),
            "current_location": candidate.get("current_location"),
            "distance_metres": distance_metres,
            "haversine_distance_metres": int(candidate["haversine_distance_metres"]),
            "eta_seconds": eta_seconds,
            "eta_display": candidate.get("eta_display") or eta_display(eta_seconds),
            "route_type": candidate.get("route_type"),
            "fit_score": candidate["fit_score"],
            "fit_breakdown": candidate["fit_breakdown"],
            "recommendation_reason": candidate["recommendation_reason"],
        }
        if candidate["resource_type"] == "officer":
            item.update(
                {
                    "officer_id": candidate.get("officer_id"),
                    "name": candidate.get("name"),
                    "badge": candidate.get("badge"),
                    "contact": candidate.get("contact"),
                }
            )
        else:
            item.update(
                {
                    "vehicle_id": candidate.get("vehicle_id"),
                    "name": candidate.get("name"),
                    "badge": candidate.get("badge"),
                    "fuel_percentage": candidate.get("fuel_percentage"),
                    "capacity": candidate.get("capacity"),
                    "type": candidate.get("type"),
                }
            )
        return item

    async def find(self, payload: dict[str, Any], internal_key: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        self._validate_internal_key(internal_key)
        if payload.get("request_type") != "find_responders":
            raise ValueError("request_type must be find_responders")
        request_id = payload.get("request_id")
        org_id = payload.get("org_id")
        incident = payload.get("incident") or {}
        location = incident.get("location") or {}
        requirements = incident.get("requirements") or {}
        options = payload.get("options") or {}
        if not request_id:
            raise ValueError("request_id is required")
        if not org_id:
            raise ValueError("org_id is required")
        if not incident.get("id"):
            raise ValueError("incident.id is required")
        if "lat" not in location or "lng" not in location:
            raise ValueError("incident.location.lat and incident.location.lng are required")

        search_radius_km = float(options.get("search_radius_km") or self.settings.default_search_radius_km)
        max_candidates = int(options.get("max_candidates") or self.settings.default_max_candidates)
        include_vehicles = bool(options.get("include_vehicles", False) or int(requirements.get("vehicles_needed") or 0) > 0)
        request_eta = bool(options.get("request_eta_from_route_calculator", True))

        incident_lat = float(location["lat"])
        incident_lng = float(location["lng"])
        min_lat, max_lat, min_lng, max_lng = bounding_box(incident_lat, incident_lng, search_radius_km)

        officers = self.store.fetch_officers(org_id)
        vehicles = self.store.fetch_vehicles(org_id) if include_vehicles or int(requirements.get("vehicles_needed") or 0) > 0 else []
        active_incidents = self.store.fetch_active_incidents(org_id, incident.get("id"))
        assigned_ids = {officer_id for active in active_incidents for officer_id in active.get("assigned_officer_ids", [])}

        total_on_shift = 0
        officer_candidates: list[dict[str, Any]] = []
        vehicle_candidates: list[dict[str, Any]] = []
        excluded_officers: list[dict[str, Any]] = []
        excluded_vehicle_count = 0

        for officer in officers:
            is_valid, reason = self._base_officer_filter(officer, incident, assigned_ids)
            if not is_valid:
                excluded_officers.append(
                    {
                        "officer_id": officer.get("officer_id"),
                        "name": officer.get("name"),
                        "reason": reason,
                        "detail": self._officer_exclusion_detail(officer, reason),
                    }
                )
                continue
            total_on_shift += 1
            lat = float(officer["current_lat"])
            lng = float(officer["current_lng"])
            if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
                continue
            candidate = self._prepare_officer_candidate(officer, incident)
            officer_candidates.append(candidate)

        for vehicle in vehicles:
            is_valid, reason = self._base_vehicle_filter(vehicle)
            if not is_valid:
                excluded_vehicle_count += 1
                continue
            lat = float(vehicle["current_lat"])
            lng = float(vehicle["current_lng"])
            if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
                continue
            candidate = self._prepare_vehicle_candidate(vehicle, incident)
            vehicle_candidates.append(candidate)

        # Indoor incidents prioritise officers already inside the building.
        if location.get("indoor") and location.get("building_id"):
            officer_candidates.sort(key=lambda item: (0 if item.get("current_building_id") == location.get("building_id") else 1, item["haversine_distance_metres"]))
        else:
            officer_candidates.sort(key=lambda item: item["haversine_distance_metres"])
        vehicle_candidates.sort(key=lambda item: item["haversine_distance_metres"])

        candidates: list[dict[str, Any]] = officer_candidates
        if include_vehicles:
            candidates = officer_candidates + vehicle_candidates

        route_calculator_called = False
        candidates_sent_to_route_calculator = 0
        if request_eta and candidates:
            try:
                route_calculator_called, candidates_sent_to_route_calculator, candidates = await self._route_calculator_etAs(payload, candidates, incident)
            except Exception:
                route_calculator_called = True

        recommendations = [self._build_recommendation(candidate, incident) for candidate in candidates]
        recommendations.sort(key=lambda item: (-item["fit_score"], item["eta_seconds"] is None, item["eta_seconds"] or 10**9, item["distance_metres"]))

        recommended_officers = [item for item in recommendations if "officer_id" in item][: max_candidates]
        recommended_vehicles = [item for item in recommendations if "vehicle_id" in item][: max(0, int(requirements.get("vehicles_needed") or 0))]

        for index, item in enumerate(recommended_officers, start=1):
            item["rank"] = index
        for index, item in enumerate(recommended_vehicles, start=1):
            item["rank"] = index

        primary = recommendations[0] if recommendations else None

        warnings: list[str] = []
        if not route_calculator_called or not self.settings.route_calculator_url:
            warnings.append("ETAs unavailable - ranked by approximate distance only")
        if location.get("indoor") and not any(item.get("current_building_id") == location.get("building_id") for item in officer_candidates):
            warnings.append("Indoor location - GPS approximate, verify officer position")

        excluded = excluded_officers
        if excluded_vehicle_count:
            excluded.append(
                {
                    "vehicle_id": None,
                    "name": None,
                    "reason": "vehicle_filters_applied",
                    "detail": f"{excluded_vehicle_count} vehicles excluded by availability or staleness checks",
                }
            )

        summary = {
            "fastest_responder": (primary.get("officer_id") or primary.get("vehicle_id")) if primary else None,
            "fastest_eta_seconds": primary.get("eta_seconds") if primary else None,
            "officers_available_in_area": len(officer_candidates),
            "officers_recommended": len(recommended_officers),
            "all_requirements_met": len(recommended_officers) >= int(requirements.get("officers_needed") or 0)
            and len(recommended_vehicles) >= int(requirements.get("vehicles_needed") or 0),
            "warnings": warnings,
        }

        result = {
            "request_id": request_id,
            "status": "success",
            "data": {
                "incident_id": incident.get("id"),
                "search_radius_km": search_radius_km,
                "total_on_shift": total_on_shift,
                "total_candidates_found": len(officer_candidates) + len(vehicle_candidates),
                "recommended_officers": recommended_officers,
                "recommended_vehicles": recommended_vehicles if include_vehicles else [],
                "excluded_officers": excluded,
                "summary": summary,
            },
            "meta": {
                "query_time_ms": int((time.perf_counter() - started) * 1000),
                "route_calculator_called": route_calculator_called,
                "candidates_sent_to_route_calculator": candidates_sent_to_route_calculator,
            },
        }

        self.store.save_query_log(
            {
                "request_id": request_id,
                "incident_id": incident.get("id"),
                "org_id": org_id,
                "incident_lat": incident_lat,
                "incident_lng": incident_lng,
                "search_radius_km": search_radius_km,
                "total_on_shift": total_on_shift,
                "candidates_found": len(officer_candidates) + len(vehicle_candidates),
                "officers_recommended": len(recommended_officers),
                "fastest_eta_seconds": summary["fastest_eta_seconds"],
                "route_calculator_called": route_calculator_called,
                "query_time_ms": result["meta"]["query_time_ms"],
            }
        )

        return result

    def _officer_exclusion_detail(self, officer: dict[str, Any], reason: str | None) -> str:
        if reason == "location_stale":
            stale = self._stale_seconds(officer.get("location_updated_at"))
            if stale is not None:
                return f"Last location update {stale // 60} minutes ago"
            return "Location update is stale"
        if reason == "already_responding":
            incident_id = officer.get("assigned_incident_id")
            return f"Currently assigned to {incident_id}" if incident_id else "Already assigned to an active incident"
        if reason == "not_on_shift":
            return "Officer is not on shift"
        if reason == "location_unknown":
            return "Officer has no current location"
        return "Excluded by dispatch rules"
