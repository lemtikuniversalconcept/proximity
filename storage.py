from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None  # type: ignore


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _stable_uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str(value)))


def _demo_officers() -> list[dict[str, Any]]:
    return [
        {
            "id": _stable_uuid("off-001"),
            "org_id": "org_abc123",
            "officer_id": "OFF-001",
            "name": "Ahmed Bello",
            "badge_number": "LG-0042",
            "status": "available",
            "armed": True,
            "weapon_id": _stable_uuid("weapon-001"),
            "rank": "Sergeant",
            "certifications": ["armed_response", "first_aid"],
            "contact": "+234XXXXXXXXXX",
            "assigned_zone": "Eko Hotel",
            "current_lat": 6.4290,
            "current_lng": 3.4230,
            "current_building_id": "BLDG-EKO-HOTEL",
            "current_floor": 1,
            "location_updated_at": _utcnow(),
            "shift_start": _utcnow(),
            "shift_end": None,
            "hours_on_shift": 4.5,
            "equipment_carried": ["body_armour", "radio", "cuffs", "medical_kit"],
        },
        {
            "id": _stable_uuid("off-003"),
            "org_id": "org_abc123",
            "officer_id": "OFF-003",
            "name": "Grace Okonkwo",
            "badge_number": "LG-0061",
            "status": "available",
            "armed": False,
            "weapon_id": None,
            "rank": "Constable",
            "certifications": ["first_aid", "tactical"],
            "contact": "+234XXXXXXXXXX",
            "assigned_zone": "Eko Hotel",
            "current_lat": 6.4275,
            "current_lng": 3.4210,
            "current_building_id": "BLDG-EKO-HOTEL",
            "current_floor": 2,
            "location_updated_at": _utcnow(),
            "shift_start": _utcnow(),
            "shift_end": None,
            "hours_on_shift": 6.2,
            "equipment_carried": ["radio", "cuffs", "medical_kit"],
        },
        {
            "id": _stable_uuid("off-007"),
            "org_id": "org_abc123",
            "officer_id": "OFF-007",
            "name": "Emeka Nwosu",
            "badge_number": "LG-0089",
            "status": "available",
            "armed": True,
            "weapon_id": _stable_uuid("weapon-007"),
            "rank": "Corporal",
            "certifications": ["armed_response"],
            "contact": "+234XXXXXXXXXX",
            "assigned_zone": "Marina",
            "current_lat": 6.4265,
            "current_lng": 3.4200,
            "current_building_id": "BLDG-EKO-HOTEL",
            "current_floor": 0,
            "location_updated_at": _utcnow(),
            "shift_start": _utcnow(),
            "shift_end": None,
            "hours_on_shift": 8.1,
            "equipment_carried": ["body_armour", "radio"],
        },
        {
            "id": _stable_uuid("off-009"),
            "org_id": "org_abc123",
            "officer_id": "OFF-009",
            "name": "Bola Adeyemi",
            "badge_number": "LG-0101",
            "status": "available",
            "armed": False,
            "weapon_id": None,
            "rank": "Constable",
            "certifications": ["crowd_control"],
            "contact": "+234XXXXXXXXXX",
            "assigned_zone": "Ikoyi",
            "current_lat": 6.4700,
            "current_lng": 3.3900,
            "current_building_id": None,
            "current_floor": None,
            "location_updated_at": _utcnow(),
            "shift_start": _utcnow(),
            "shift_end": None,
            "hours_on_shift": 9.0,
            "equipment_carried": ["radio"],
        },
        {
            "id": _stable_uuid("off-011"),
            "org_id": "org_abc123",
            "officer_id": "OFF-011",
            "name": "Tunde Fashola",
            "badge_number": "LG-0127",
            "status": "available",
            "armed": True,
            "weapon_id": _stable_uuid("weapon-011"),
            "rank": "Inspector",
            "certifications": ["negotiation", "first_aid"],
            "contact": "+234XXXXXXXXXX",
            "assigned_zone": "Victoria Island",
            "current_lat": 6.4500,
            "current_lng": 3.4100,
            "current_building_id": None,
            "current_floor": None,
            "location_updated_at": _utcnow(),
            "shift_start": _utcnow(),
            "shift_end": None,
            "hours_on_shift": 11.4,
            "equipment_carried": ["body_armour", "radio", "medical_kit"],
            "assigned_incident_id": "INC-2024-000",
        },
    ]


def _demo_vehicles() -> list[dict[str, Any]]:
    return [
        {
            "id": _stable_uuid("veh-001"),
            "org_id": "org_abc123",
            "vehicle_id": "VEH-001",
            "plate_number": "LAG-201-TRK",
            "type": "patrol_car",
            "status": "available",
            "fuel_percentage": 72,
            "fuel_litres": 40.0,
            "condition": "good",
            "capacity": 4,
            "assigned_driver_id": _stable_uuid("off-001"),
            "current_lat": 6.4288,
            "current_lng": 3.4222,
            "location_updated_at": _utcnow(),
            "hours_on_shift": 4.5,
            "special_equipment": ["radio"],
        },
        {
            "id": _stable_uuid("veh-002"),
            "org_id": "org_abc123",
            "vehicle_id": "VEH-002",
            "plate_number": "LAG-404-TRK",
            "type": "patrol_car",
            "status": "available",
            "fuel_percentage": 54,
            "fuel_litres": 31.0,
            "condition": "good",
            "capacity": 5,
            "assigned_driver_id": None,
            "current_lat": 6.4310,
            "current_lng": 3.4195,
            "location_updated_at": _utcnow(),
            "hours_on_shift": 5.0,
            "special_equipment": ["radio", "first_aid_kit"],
        },
        {
            "id": _stable_uuid("veh-003"),
            "org_id": "org_abc123",
            "vehicle_id": "VEH-003",
            "plate_number": "LAG-777-BUS",
            "type": "response_van",
            "status": "available",
            "fuel_percentage": 35,
            "fuel_litres": 48.0,
            "condition": "good",
            "capacity": 8,
            "assigned_driver_id": _stable_uuid("off-007"),
            "current_lat": 6.4250,
            "current_lng": 3.4215,
            "location_updated_at": _utcnow(),
            "hours_on_shift": 8.0,
            "special_equipment": ["medical_kit"],
        },
    ]


def _demo_incidents() -> list[dict[str, Any]]:
    return [
        {
            "id": "INC-2024-000",
            "org_id": "org_abc123",
            "status": "in_progress",
            "assigned_officer_ids": ["OFF-011"],
        }
    ]


@dataclass
class ProximityStore:
    database_url: str | None
    local_database_path: Path

    def __post_init__(self) -> None:
        self.local_database_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_url:
            self._init_postgres()
        else:
            self._init_sqlite()

    def _init_postgres(self) -> None:
        if psycopg2 is None:
            return
        with psycopg2.connect(self.database_url) as conn:  # type: ignore[arg-type]
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS services")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS services.proximity_queries (
                        id UUID PRIMARY KEY,
                        request_id VARCHAR(100) UNIQUE NOT NULL,
                        incident_id VARCHAR(100) NOT NULL,
                        org_id VARCHAR(100) NOT NULL,
                        incident_lat NUMERIC(10,8),
                        incident_lng NUMERIC(11,8),
                        search_radius_km NUMERIC(5,2),
                        total_on_shift INTEGER,
                        candidates_found INTEGER,
                        officers_recommended INTEGER,
                        fastest_eta_seconds INTEGER,
                        route_calculator_called BOOLEAN DEFAULT FALSE,
                        query_time_ms INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
            conn.commit()

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.local_database_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS officers (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    officer_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    badge_number TEXT NOT NULL UNIQUE,
                    status TEXT DEFAULT 'off_duty',
                    armed INTEGER DEFAULT 0,
                    weapon_id TEXT,
                    rank TEXT,
                    certifications TEXT DEFAULT '[]',
                    contact TEXT,
                    assigned_zone TEXT,
                    current_lat REAL,
                    current_lng REAL,
                    current_building_id TEXT,
                    current_floor INTEGER,
                    location_updated_at TEXT,
                    shift_start TEXT,
                    shift_end TEXT,
                    hours_on_shift REAL DEFAULT 0,
                    equipment_carried TEXT DEFAULT '[]',
                    assigned_incident_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicles (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    vehicle_id TEXT UNIQUE NOT NULL,
                    plate_number TEXT,
                    type TEXT,
                    status TEXT DEFAULT 'available',
                    fuel_percentage INTEGER DEFAULT 0,
                    fuel_litres REAL DEFAULT 0,
                    condition TEXT DEFAULT 'good',
                    capacity INTEGER DEFAULT 4,
                    assigned_driver_id TEXT,
                    current_lat REAL,
                    current_lng REAL,
                    location_updated_at TEXT,
                    hours_on_shift REAL DEFAULT 0,
                    special_equipment TEXT DEFAULT '[]'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_officer_ids TEXT DEFAULT '[]'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proximity_queries (
                    id TEXT PRIMARY KEY,
                    request_id TEXT UNIQUE NOT NULL,
                    incident_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    incident_lat REAL,
                    incident_lng REAL,
                    search_radius_km REAL,
                    total_on_shift INTEGER,
                    candidates_found INTEGER,
                    officers_recommended INTEGER,
                    fastest_eta_seconds INTEGER,
                    route_calculator_called INTEGER DEFAULT 0,
                    query_time_ms INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            if not self._has_rows(conn, "officers"):
                self._seed_sqlite(conn)

    def _seed_sqlite(self, conn: sqlite3.Connection) -> None:
        for row in _demo_officers():
            conn.execute(
                """
                INSERT INTO officers (
                    id, org_id, officer_id, name, badge_number, status, armed, weapon_id, rank, certifications,
                    contact, assigned_zone, current_lat, current_lng, current_building_id, current_floor,
                    location_updated_at, shift_start, shift_end, hours_on_shift, equipment_carried, assigned_incident_id
                ) VALUES (
                    :id, :org_id, :officer_id, :name, :badge_number, :status, :armed, :weapon_id, :rank, :certifications,
                    :contact, :assigned_zone, :current_lat, :current_lng, :current_building_id, :current_floor,
                    :location_updated_at, :shift_start, :shift_end, :hours_on_shift, :equipment_carried, :assigned_incident_id
                )
                """,
                {
                    **row,
                    "armed": 1 if row.get("armed") else 0,
                    "certifications": _json_dumps(row.get("certifications", [])),
                    "equipment_carried": _json_dumps(row.get("equipment_carried", [])),
                    "assigned_incident_id": row.get("assigned_incident_id"),
                },
            )
        for row in _demo_vehicles():
            conn.execute(
                """
                INSERT INTO vehicles (
                    id, org_id, vehicle_id, plate_number, type, status, fuel_percentage, fuel_litres, condition,
                    capacity, assigned_driver_id, current_lat, current_lng, location_updated_at, hours_on_shift,
                    special_equipment
                ) VALUES (
                    :id, :org_id, :vehicle_id, :plate_number, :type, :status, :fuel_percentage, :fuel_litres, :condition,
                    :capacity, :assigned_driver_id, :current_lat, :current_lng, :location_updated_at, :hours_on_shift,
                    :special_equipment
                )
                """,
                {
                    **row,
                    "special_equipment": _json_dumps(row.get("special_equipment", [])),
                },
            )
        for row in _demo_incidents():
            conn.execute(
                """
                INSERT INTO incidents (id, org_id, status, assigned_officer_ids)
                VALUES (:id, :org_id, :status, :assigned_officer_ids)
                """,
                {**row, "assigned_officer_ids": _json_dumps(row.get("assigned_officer_ids", []))},
            )
        conn.commit()

    def _has_rows(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return bool(row and int(row["count"]) > 0)

    def _sqlite_fetch(self, table: str, org_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.local_database_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT * FROM {table} WHERE org_id = ? ORDER BY created_at DESC", (org_id,)).fetchall() if table == "proximity_queries" else conn.execute(f"SELECT * FROM {table} WHERE org_id = ? ORDER BY id", (org_id,)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["armed"] = bool(item.get("armed")) if "armed" in item else item.get("armed")
            item["certifications"] = _json_loads(item.get("certifications"), [])
            item["equipment_carried"] = _json_loads(item.get("equipment_carried"), [])
            item["special_equipment"] = _json_loads(item.get("special_equipment"), [])
            item["assigned_officer_ids"] = _json_loads(item.get("assigned_officer_ids"), [])
            result.append(item)
        return result

    def fetch_officers(self, org_id: str) -> list[dict[str, Any]]:
        if self.database_url and psycopg2 is not None:
            sql = """
                SELECT
                    o.id,
                    o.org_id,
                    COALESCE(o.officer_id, o.badge_number) AS officer_id,
                    o.name,
                    o.badge_number,
                    o.status,
                    o.armed,
                    o.weapon_id,
                    o.rank,
                    o.certifications,
                    o.contact,
                    o.assigned_zone,
                    o.current_lat,
                    o.current_lng,
                    o.location_updated_at,
                    o.shift_start,
                    o.shift_end,
                    EXTRACT(EPOCH FROM (NOW() - o.shift_start)) / 3600 AS hours_on_shift,
                    NULL::text AS current_building_id,
                    NULL::integer AS current_floor,
                    NULL::jsonb AS equipment_carried
                FROM inventory.officers o
                WHERE o.org_id = %s
            """
            with psycopg2.connect(self.database_url) as conn:  # type: ignore[arg-type]
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (org_id,))
                    rows = cur.fetchall()
            return [self._normalize_officer(dict(row)) for row in rows]
        return [self._normalize_officer(row) for row in self._sqlite_fetch("officers", org_id)]

    def fetch_vehicles(self, org_id: str) -> list[dict[str, Any]]:
        if self.database_url and psycopg2 is not None:
            sql = """
                SELECT
                    v.id,
                    v.org_id,
                    v.vehicle_id,
                    v.plate_number,
                    v.type,
                    v.status,
                    v.fuel_percentage,
                    v.fuel_litres,
                    v.condition,
                    v.capacity,
                    v.assigned_driver_id,
                    v.current_lat,
                    v.current_lng,
                    v.location_updated_at,
                    NULL::numeric AS hours_on_shift,
                    v.special_equipment
                FROM inventory.vehicles v
                WHERE v.org_id = %s
            """
            with psycopg2.connect(self.database_url) as conn:  # type: ignore[arg-type]
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (org_id,))
                    rows = cur.fetchall()
            return [self._normalize_vehicle(dict(row)) for row in rows]
        return [self._normalize_vehicle(row) for row in self._sqlite_fetch("vehicles", org_id)]

    def fetch_active_incidents(self, org_id: str, current_incident_id: str | None) -> list[dict[str, Any]]:
        if self.database_url and psycopg2 is not None:
            sql = """
                SELECT i.id, i.assigned_officer_ids
                FROM sod.incidents i
                WHERE i.org_id = %s
                  AND i.status NOT IN ('resolved', 'closed', 'escalated_closed')
                  AND (%s IS NULL OR i.id <> %s)
            """
            with psycopg2.connect(self.database_url) as conn:  # type: ignore[arg-type]
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (org_id, current_incident_id, current_incident_id))
                    rows = cur.fetchall()
            return [{"id": row["id"], "assigned_officer_ids": _json_loads(row.get("assigned_officer_ids"), [])} for row in rows]
        incidents = [row for row in self._sqlite_fetch("incidents", org_id) if row.get("id") != current_incident_id]
        return [{"id": row["id"], "assigned_officer_ids": row.get("assigned_officer_ids", [])} for row in incidents]

    def save_query_log(self, entry: dict[str, Any]) -> None:
        if self.database_url and psycopg2 is not None:
            sql = """
                INSERT INTO services.proximity_queries (
                    id, request_id, incident_id, org_id, incident_lat, incident_lng, search_radius_km,
                    total_on_shift, candidates_found, officers_recommended, fastest_eta_seconds,
                    route_calculator_called, query_time_ms
                ) VALUES (
                    %(id)s, %(request_id)s, %(incident_id)s, %(org_id)s, %(incident_lat)s, %(incident_lng)s, %(search_radius_km)s,
                    %(total_on_shift)s, %(candidates_found)s, %(officers_recommended)s, %(fastest_eta_seconds)s,
                    %(route_calculator_called)s, %(query_time_ms)s
                )
                ON CONFLICT (request_id) DO UPDATE SET
                    incident_id = EXCLUDED.incident_id,
                    org_id = EXCLUDED.org_id,
                    incident_lat = EXCLUDED.incident_lat,
                    incident_lng = EXCLUDED.incident_lng,
                    search_radius_km = EXCLUDED.search_radius_km,
                    total_on_shift = EXCLUDED.total_on_shift,
                    candidates_found = EXCLUDED.candidates_found,
                    officers_recommended = EXCLUDED.officers_recommended,
                    fastest_eta_seconds = EXCLUDED.fastest_eta_seconds,
                    route_calculator_called = EXCLUDED.route_calculator_called,
                    query_time_ms = EXCLUDED.query_time_ms
            """
            payload = {**entry, "id": entry.get("id") or _stable_uuid(entry["request_id"]) }
            with psycopg2.connect(self.database_url) as conn:  # type: ignore[arg-type]
                with conn.cursor() as cur:
                    cur.execute(sql, payload)
                conn.commit()
            return
        with sqlite3.connect(self.local_database_path) as conn:
            conn.execute(
                """
                INSERT INTO proximity_queries (
                    id, request_id, incident_id, org_id, incident_lat, incident_lng, search_radius_km,
                    total_on_shift, candidates_found, officers_recommended, fastest_eta_seconds,
                    route_calculator_called, query_time_ms
                ) VALUES (
                    :id, :request_id, :incident_id, :org_id, :incident_lat, :incident_lng, :search_radius_km,
                    :total_on_shift, :candidates_found, :officers_recommended, :fastest_eta_seconds,
                    :route_calculator_called, :query_time_ms
                )
                ON CONFLICT(request_id) DO UPDATE SET
                    incident_id = excluded.incident_id,
                    org_id = excluded.org_id,
                    incident_lat = excluded.incident_lat,
                    incident_lng = excluded.incident_lng,
                    search_radius_km = excluded.search_radius_km,
                    total_on_shift = excluded.total_on_shift,
                    candidates_found = excluded.candidates_found,
                    officers_recommended = excluded.officers_recommended,
                    fastest_eta_seconds = excluded.fastest_eta_seconds,
                    route_calculator_called = excluded.route_calculator_called,
                    query_time_ms = excluded.query_time_ms
                """,
                {
                    **entry,
                    "id": entry.get("id") or _stable_uuid(entry["request_id"]),
                },
            )
            conn.commit()

    def list_queries(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        if self.database_url and psycopg2 is not None:
            sql = """
                SELECT
                    id, request_id, incident_id, org_id, incident_lat, incident_lng, search_radius_km,
                    total_on_shift, candidates_found, officers_recommended, fastest_eta_seconds,
                    route_calculator_called, query_time_ms, created_at
                FROM services.proximity_queries
                ORDER BY created_at DESC
                LIMIT %s
            """
            with psycopg2.connect(self.database_url) as conn:  # type: ignore[arg-type]
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (limit,))
                    return [dict(row) for row in cur.fetchall()]
        with sqlite3.connect(self.local_database_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    id, request_id, incident_id, org_id, incident_lat, incident_lng, search_radius_km,
                    total_on_shift, candidates_found, officers_recommended, fastest_eta_seconds,
                    route_calculator_called, query_time_ms, created_at
                FROM proximity_queries
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "backend": "postgres" if self.database_url else "sqlite",
            "database_connected": True,
        }

    def _normalize_officer(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["armed"] = bool(row.get("armed"))
        row["certifications"] = _json_loads(row.get("certifications"), [])
        row["equipment_carried"] = _json_loads(row.get("equipment_carried"), [])
        row["hours_on_shift"] = float(row.get("hours_on_shift") or 0.0)
        return row

    def _normalize_vehicle(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["special_equipment"] = _json_loads(row.get("special_equipment"), [])
        row["fuel_percentage"] = int(row.get("fuel_percentage") or 0)
        row["hours_on_shift"] = float(row.get("hours_on_shift") or 0.0)
        return row


def create_store(database_url: str | None, local_database_path: Path) -> ProximityStore:
    return ProximityStore(database_url=database_url, local_database_path=local_database_path)
