# Lemtik Security — Proximity & Officer Finder Service Specification
### Service 3 of 6 — On-Demand Dispatch Intelligence
**Classification:** Internal Engineering
**Version:** 1.0
**Status:** Build-Ready

---

## 1. What This Service Is

The Proximity & Officer Finder Service is an on-demand service
that activates exclusively when an incident is logged. Its sole
purpose is to answer one question with precision:

**"Given this incident at this location, which available
officers and vehicles should we send — and in what order?"**

It does not run continuously. It does not monitor thresholds.
It does not track officers when no incident is active.
It runs, answers the question, and returns a ranked
recommendation to the Master Agent through the
Relationship API.

---

## 2. Distinction From Inventory Service

This is critical. Both services deal with officers and
vehicles but they serve completely different purposes.

```
Inventory Service
  — Always running, 24/7
  — Knows what resources EXIST and their status
  — Tracks availability, fuel, condition, equipment
  — Flags when thresholds are breached
  — Never triggered by incidents
  — Answers: "What do we have?"

Proximity & Officer Finder
  — On-demand only, triggered by incident
  — Knows which resources are CLOSEST to a location
  — Ranks by distance, capability, and fit
  — Only queries on-shift officers and available vehicles
  — Never runs without an active incident
  — Answers: "Who should we send?"
```

They share the same database tables but read different
things from them and serve completely different masters.

---

## 3. Position in the Flow

```
Incident logged on C4I Dashboard
        ↓
Dashboard → Relationship API
        ↓
Relationship API → Master Agent
        ↓
Master Agent analyses incident
determines resources are needed
sends job manifest to Relationship API:
{
  jobs: ["find_closest_officers", "find_closest_vehicles", ...]
}
        ↓
Relationship API → Proximity & Officer Finder
(in parallel with other services)
        ↓
Proximity Finder:
  1. Reads incident location
  2. Queries all on-shift officers + available vehicles
  3. Calculates true distance to incident for each
  4. Filters by capability match
  5. Ranks by proximity + fit score
  6. Returns ranked recommendation list
        ↓
Relationship API collects output
sends to Master Agent
        ↓
Master Agent includes ranked officers
in recommendation panel returned to dashboard
        ↓
Operator sees: "Recommended officers: Ahmed (800m),
Chidi (1.2km), Grace (1.8km)"
Operator pings them directly from the panel
```

---

## 4. What It Considers

### 4.1 Distance Calculation

The service calculates the real-world distance from each
officer or vehicle to the incident location.

**Not straight-line distance.**
A straight-line calculation is useless in Lagos — it ignores
roads, water, and barriers. The Proximity Finder uses the
Haversine formula for a fast initial filter, then passes
the top candidates to the Route Calculator for true
road-network distance.

```
Step 1 — Haversine filter (fast, runs in milliseconds)
  Filter all on-shift officers down to those within
  a configurable radius (default: 5km straight-line)
  This eliminates obviously distant officers instantly

Step 2 — Road-network distance (accurate, via Valhalla)
  For the filtered candidates only, request true
  travel distance and ETA from the Route Calculator
  This gives real travel time, not crow-flies distance
```

### 4.2 Capability Matching

Distance alone is not enough. The service filters and scores
officers against what the incident actually requires.

**Capability factors:**

```
Armed status
  — Does the incident require armed response?
  — Is this officer armed and carrying the right weapon?

Certifications
  — armed_response: can carry and use firearms
  — first_aid: can provide medical assistance
  — tactical: trained for high-risk entry
  — k9: dog handler
  — crowd_control: trained for civil unrest situations
  — negotiation: hostage or standoff situations

Physical status
  — Is officer currently on foot or in a vehicle?
  — Is officer already responding to another incident?
  — Has officer been on shift for more than 10 hours?
    (flag as fatigued — not excluded but noted)

Equipment carried
  — What does the officer have on them right now?
  — Body armour, radio, cuffs, medical kit?
```

**Vehicle capability factors:**

```
Fuel level
  — Is fuel sufficient for round trip to incident?
  — Flag if return journey may be marginal

Vehicle type match
  — Does the incident need a specific vehicle type?
  — Riot? → truck. Pursuit? → patrol car. Waterway? → boat.

Capacity
  — How many officers does it need to carry?
  — Is the vehicle large enough?

Current location
  — Is the vehicle at base or already deployed nearby?

Driver availability
  — Is an available driver assigned?
  — Can any available officer drive it?
```

### 4.3 Fit Score

Every candidate officer and vehicle receives a composite
fit score (0–100) combining:

```python
def calculate_fit_score(
    officer: dict,
    incident: dict,
    distance_metres: int,
    eta_seconds: int
) -> float:

    score = 100.0

    # Distance penalty (heavier penalty beyond 1km)
    if distance_metres <= 500:
        score -= 0
    elif distance_metres <= 1000:
        score -= 10
    elif distance_metres <= 2000:
        score -= 25
    elif distance_metres <= 3000:
        score -= 40
    else:
        score -= 60

    # Armed requirement
    if incident.get("armed_required") and not officer.get("armed"):
        score -= 40  # Major penalty — not eliminated but deprioritised

    # Certification match
    required_certs = incident.get("required_certifications", [])
    officer_certs = officer.get("certifications", [])
    matched = len(set(required_certs) & set(officer_certs))
    total_required = len(required_certs)
    if total_required > 0:
        score += (matched / total_required) * 15

    # Fatigue flag (on shift > 10 hours)
    if officer.get("hours_on_shift", 0) > 10:
        score -= 15

    # Already at incident area (bonus)
    if distance_metres < 100:
        score += 10

    return max(0.0, min(100.0, score))
```

---

## 5. On-Shift Only Rule

Officers are only tracked and considered for dispatch
when they are actively on shift.

**What "on shift" means:**
- Officer clocked in via the mobile app at shift start
- Shift has not ended or been manually closed
- Officer has not been manually set to off_duty by supervisor
- Officer location has been updated within the last 5 minutes
  (stale location = officer is treated as unavailable)

**If officer location is older than 5 minutes:**
```
Officer is flagged as "location unknown"
Not recommended for dispatch
Supervisor sees: "Officer Ahmed — location last updated
8 minutes ago. Cannot confirm position."
```

**Privacy guarantee:**
Location tracking stops the moment an officer clocks out.
No location data is stored after shift end.
This is enforced at the database level —
location fields are nulled when shift closes.

---

## 6. Input & Output Contract

### 6.1 Input from Relationship API

```json
{
  "request_type": "find_responders",
  "request_id": "req_prox_001",
  "org_id": "org_abc123",
  "incident": {
    "id": "INC-2024-001",
    "type": "assault",
    "severity": 4,
    "description": "Man being stabbed, North West Wing Floor 3",
    "location": {
      "name": "North West Wing, Floor 3, Eko Hotel",
      "lat": 6.4281,
      "lng": 3.4219,
      "building_id": "BLDG-EKO-HOTEL",
      "floor": 3,
      "indoor": true
    },
    "requirements": {
      "officers_needed": 3,
      "armed_required": false,
      "certifications_preferred": ["first_aid", "tactical"],
      "vehicles_needed": 0,
      "priority": "immediate"
    }
  },
  "options": {
    "search_radius_km": 5,
    "max_candidates": 10,
    "include_vehicles": false,
    "request_eta_from_route_calculator": true
  }
}
```

### 6.2 Output to Relationship API

```json
{
  "request_id": "req_prox_001",
  "status": "success",
  "data": {
    "incident_id": "INC-2024-001",
    "search_radius_km": 5,
    "total_on_shift": 12,
    "total_candidates_found": 7,
    "recommended_officers": [
      {
        "rank": 1,
        "officer_id": "OFF-001",
        "name": "Ahmed Bello",
        "badge": "LG-0042",
        "contact": "+234XXXXXXXXXX",
        "status": "available",
        "armed": true,
        "weapon": "pistol",
        "certifications": ["armed_response", "first_aid"],
        "current_location": {
          "lat": 6.4290,
          "lng": 3.4230,
          "description": "Hotel Lobby",
          "last_updated": "ISO8601",
          "seconds_since_update": 45
        },
        "distance_metres": 180,
        "haversine_distance_metres": 165,
        "eta_seconds": 81,
        "eta_display": "1 min 21 sec",
        "route_type": "foot",
        "fit_score": 94,
        "fit_breakdown": {
          "distance_score": 100,
          "armed_match": true,
          "certifications_matched": ["first_aid"],
          "certifications_missing": [],
          "fatigue_flag": false,
          "hours_on_shift": 4.5
        },
        "recommendation_reason": "Closest officer, first aid certified, armed, 81s ETA"
      },
      {
        "rank": 2,
        "officer_id": "OFF-003",
        "name": "Grace Okonkwo",
        "badge": "LG-0061",
        "contact": "+234XXXXXXXXXX",
        "status": "available",
        "armed": false,
        "weapon": null,
        "certifications": ["first_aid", "tactical"],
        "current_location": {
          "lat": 6.4275,
          "lng": 3.4210,
          "description": "Car Park Level 2",
          "last_updated": "ISO8601",
          "seconds_since_update": 112
        },
        "distance_metres": 420,
        "haversine_distance_metres": 380,
        "eta_seconds": 189,
        "eta_display": "3 min 9 sec",
        "route_type": "foot",
        "fit_score": 86,
        "fit_breakdown": {
          "distance_score": 82,
          "armed_match": false,
          "certifications_matched": ["first_aid", "tactical"],
          "certifications_missing": [],
          "fatigue_flag": false,
          "hours_on_shift": 6.2
        },
        "recommendation_reason": "Both certifications matched, 3min ETA, unarmed"
      },
      {
        "rank": 3,
        "officer_id": "OFF-007",
        "name": "Emeka Nwosu",
        "badge": "LG-0089",
        "contact": "+234XXXXXXXXXX",
        "status": "available",
        "armed": true,
        "weapon": "pistol",
        "certifications": ["armed_response"],
        "current_location": {
          "lat": 6.4265,
          "lng": 3.4200,
          "description": "Main Gate",
          "last_updated": "ISO8601",
          "seconds_since_update": 78
        },
        "distance_metres": 780,
        "haversine_distance_metres": 720,
        "eta_seconds": 351,
        "eta_display": "5 min 51 sec",
        "route_type": "foot",
        "fit_score": 71,
        "fit_breakdown": {
          "distance_score": 65,
          "armed_match": true,
          "certifications_matched": [],
          "certifications_missing": ["first_aid", "tactical"],
          "fatigue_flag": false,
          "hours_on_shift": 8.1
        },
        "recommendation_reason": "Armed backup, 6min ETA, missing preferred certifications"
      }
    ],
    "recommended_vehicles": [],
    "excluded_officers": [
      {
        "officer_id": "OFF-009",
        "name": "Bola Adeyemi",
        "reason": "location_stale",
        "detail": "Last location update 12 minutes ago"
      },
      {
        "officer_id": "OFF-011",
        "name": "Tunde Fashola",
        "reason": "already_responding",
        "detail": "Currently assigned to INC-2024-000"
      }
    ],
    "summary": {
      "fastest_responder": "OFF-001",
      "fastest_eta_seconds": 81,
      "officers_available_in_area": 7,
      "officers_recommended": 3,
      "all_requirements_met": true,
      "warnings": []
    }
  },
  "meta": {
    "query_time_ms": 210,
    "route_calculator_called": true,
    "candidates_sent_to_route_calculator": 5
  }
}
```

---

## 7. Indoor Incident Handling

Lagos security operations happen in buildings —
hotels, hospitals, malls, office towers.
Indoor incidents need different proximity logic.

**Indoor incident flags:**
```json
{
  "location": {
    "indoor": true,
    "building_id": "BLDG-EKO-HOTEL",
    "floor": 3,
    "zone": "north_west_wing"
  }
}
```

**When indoor = true:**
- Officers inside the same building are ranked highest
  regardless of GPS distance (GPS is unreliable indoors)
- Officers are matched to building using their last known
  building check-in (if building has indoor positioning)
- Floor proximity is factored in if floor data is available:
  same floor > adjacent floor > different floor
- Route Calculator is told to use indoor routing profile
  (elevator, stairs, corridors) not outdoor foot routing
- If no indoor positioning, fall back to GPS with a note:
  "Indoor location — GPS approximate, verify officer position"

---

## 8. Multi-Incident Handling

When multiple incidents are active simultaneously,
the proximity finder must prevent the same officer
from being recommended for two incidents at once.

```python
def filter_already_assigned(
    candidates: list,
    active_incidents: list
) -> tuple[list, list]:
    """
    Remove officers already assigned to active incidents.
    Return (available_candidates, excluded_with_reason)
    """
    assigned_officer_ids = set()

    for incident in active_incidents:
        for officer_id in incident.get("assigned_officer_ids", []):
            assigned_officer_ids.add(officer_id)

    available = []
    excluded = []

    for candidate in candidates:
        if candidate["officer_id"] in assigned_officer_ids:
            excluded.append({
                "officer_id": candidate["officer_id"],
                "name": candidate["name"],
                "reason": "already_responding",
                "detail": f"Assigned to active incident"
            })
        else:
            available.append(candidate)

    return available, excluded
```

---

## 9. Database Queries

The service reads from two schemas —
the services schema for proximity calculations,
and the sod schema (read-only) for active incidents.

```sql
-- Get all on-shift officers with recent location updates
-- for a specific organisation
SELECT
    o.id,
    o.name,
    o.badge_number,
    o.contact,
    o.armed,
    o.weapon_id,
    o.certifications,
    o.current_lat,
    o.current_lng,
    o.location_updated_at,
    o.shift_start,
    EXTRACT(EPOCH FROM (NOW() - o.location_updated_at)) AS seconds_since_update,
    EXTRACT(EPOCH FROM (NOW() - o.shift_start)) / 3600 AS hours_on_shift
FROM inventory.officers o
WHERE
    o.org_id = $1
    AND o.status = 'available'
    AND o.shift_start IS NOT NULL
    AND o.current_lat IS NOT NULL
    AND o.current_lng IS NOT NULL
    -- Only officers with location updated in last 5 minutes
    AND o.location_updated_at >= NOW() - INTERVAL '5 minutes'
    -- Rough bounding box filter before Haversine
    AND o.current_lat BETWEEN ($2 - 0.045) AND ($2 + 0.045)
    AND o.current_lng BETWEEN ($3 - 0.045) AND ($3 + 0.045)
ORDER BY
    -- Approximate proximity sort before precise calculation
    (o.current_lat - $2)^2 + (o.current_lng - $3)^2 ASC;

-- Get available vehicles with sufficient fuel
SELECT
    v.id,
    v.vehicle_id,
    v.plate_number,
    v.type,
    v.status,
    v.fuel_percentage,
    v.fuel_litres,
    v.capacity,
    v.current_lat,
    v.current_lng,
    v.location_updated_at,
    v.assigned_driver_id
FROM inventory.vehicles v
WHERE
    v.org_id = $1
    AND v.status = 'available'
    AND v.fuel_percentage >= 25
    AND v.current_lat IS NOT NULL
    AND v.current_lng IS NOT NULL
    AND v.location_updated_at >= NOW() - INTERVAL '10 minutes'
    AND v.current_lat BETWEEN ($2 - 0.045) AND ($2 + 0.045)
    AND v.current_lng BETWEEN ($3 - 0.045) AND ($3 + 0.045)
ORDER BY
    (v.current_lat - $2)^2 + (v.current_lng - $3)^2 ASC;

-- Get active incidents to check for already-assigned officers
SELECT
    i.id,
    i.assigned_officer_ids
FROM sod.incidents i
WHERE
    i.org_id = $1
    AND i.status NOT IN ('resolved', 'closed', 'escalated_closed')
    AND i.id != $2;  -- exclude the current incident
```

---

## 10. Haversine Implementation

Fast straight-line distance calculation used for
initial filtering before route calculator is called.

```python
import math

def haversine_distance(
    lat1: float, lng1: float,
    lat2: float, lng2: float
) -> float:
    """
    Returns distance in metres between two GPS coordinates.
    Fast enough to run on hundreds of officers in milliseconds.
    """
    R = 6_371_000  # Earth radius in metres

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(d_lambda / 2) ** 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def filter_by_radius(
    candidates: list,
    incident_lat: float,
    incident_lng: float,
    radius_metres: float
) -> list:
    """
    Filter candidates to those within radius_metres.
    Adds haversine_distance_metres to each candidate.
    """
    filtered = []
    for candidate in candidates:
        dist = haversine_distance(
            candidate["current_lat"],
            candidate["current_lng"],
            incident_lat,
            incident_lng
        )
        if dist <= radius_metres:
            candidate["haversine_distance_metres"] = round(dist)
            filtered.append(candidate)

    return sorted(filtered, key=lambda x: x["haversine_distance_metres"])
```

---

## 11. Route Calculator Integration

After Haversine filtering, top candidates are sent
to the Route Calculator for true road-network ETA.

```python
import httpx

async def get_road_network_etas(
    candidates: list,
    incident_location: dict,
    request_id: str
) -> list:
    """
    Send top N candidates to Route Calculator
    for accurate ETAs. Default: top 8 candidates.
    """
    TOP_N = 8
    to_route = candidates[:TOP_N]

    responders = [
        {
            "id": c["officer_id"] if "officer_id" in c else c["vehicle_id"],
            "type": "officer_foot" if "officer_id" in c else "vehicle",
            "current_location": {
                "lat": c["current_lat"],
                "lng": c["current_lng"]
            }
        }
        for c in to_route
    ]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ROUTE_CALCULATOR_URL}/calculate",
            json={
                "request_id": f"{request_id}_eta",
                "incident": {"location": incident_location},
                "responders": responders,
                "options": {
                    "include_infrastructure_scan": False,
                    "routing_priority": "fastest"
                }
            },
            headers={"X-Internal-Key": ROUTE_CALCULATOR_KEY},
            timeout=8.0
        )

    routes = response.json().get("data", {}).get("routes", [])

    # Merge ETA data back into candidates
    route_map = {r["responder_id"]: r for r in routes}
    for candidate in to_route:
        cid = candidate.get("officer_id") or candidate.get("vehicle_id")
        route = route_map.get(cid, {})
        candidate["eta_seconds"] = route.get("estimated_time_seconds", 9999)
        candidate["eta_display"] = route.get("estimated_time_display", "Unknown")
        candidate["distance_metres"] = route.get("distance_metres",
            candidate["haversine_distance_metres"])
        candidate["route_type"] = route.get("route_type", "foot")

    # Candidates beyond TOP_N keep haversine distance only
    for candidate in candidates[TOP_N:]:
        candidate["eta_seconds"] = None
        candidate["eta_display"] = "ETA not calculated"
        candidate["distance_metres"] = candidate["haversine_distance_metres"]

    return candidates
```

---

## 12. Database Schema

```sql
-- services schema
-- No new tables needed beyond what Inventory Service created.
-- This service reads from inventory.officers and inventory.vehicles
-- and reads (never writes) from sod.incidents

-- One logging table for audit and analytics
CREATE TABLE services.proximity_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) UNIQUE NOT NULL,
    incident_id VARCHAR(100) NOT NULL,
    org_id UUID NOT NULL,
    incident_lat DECIMAL(10,8),
    incident_lng DECIMAL(11,8),
    search_radius_km DECIMAL(5,2),
    total_on_shift INTEGER,
    candidates_found INTEGER,
    officers_recommended INTEGER,
    fastest_eta_seconds INTEGER,
    route_calculator_called BOOLEAN DEFAULT FALSE,
    query_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 13. Tech Stack

```
Language:     Python 3.11+
Framework:    FastAPI
Database:     Supabase PostgreSQL (services + sod schemas, read-only on sod)
Distance:     Haversine (pure Python, no external dependency)
ETA:          Route Calculator Service (internal call)
HTTP Client:  httpx (async)
Hosting:      Render web service
Cost:         $7/month (Starter plan)
AI Model:     None needed — pure algorithmic ranking
```

No AI model is needed here. The ranking logic is
deterministic and algorithmic. Adding an LLM would
add latency and cost with no benefit. The Master Agent
above this service applies the intelligence layer —
this service just finds and ranks candidates accurately.

---

## 14. Environment Variables

```env
DATABASE_URL=
INTERNAL_API_KEY=
ROUTE_CALCULATOR_URL=
ROUTE_CALCULATOR_KEY=
RELATIONSHIP_API_URL=
RELATIONSHIP_API_KEY=

# Defaults (overridable per request)
DEFAULT_SEARCH_RADIUS_KM=5
DEFAULT_MAX_CANDIDATES=10
MAX_LOCATION_STALENESS_SECONDS=300
MAX_VEHICLE_LOCATION_STALENESS_SECONDS=600
ROUTE_CALCULATOR_TOP_N=8

ENVIRONMENT=production
PORT=8000
```

---

## 15. API Endpoints

```
POST /find              — Main endpoint, find and rank responders
GET  /health            — Service health check
GET  /queries           — Recent query log (admin only)
```

That is it. This service does one thing.
It does not need more endpoints than this.

---

## 16. Performance Requirements

This service is in the critical path of emergency response.
Speed is non-negotiable.

```
Target response times:
  Haversine filter only:          < 50ms
  With Route Calculator ETAs:     < 500ms
  Full response to Relationship API: < 600ms

If Route Calculator is unavailable:
  Return Haversine-ranked results with flag:
  "ETAs unavailable — ranked by approximate distance only"
  Never block or fail because Route Calculator is down
```

---

## 17. Build Checklist

Before pushing to Render:

- [ ] Haversine filter tested with Lagos coordinates
- [ ] Bounding box pre-filter tested (performance)
- [ ] On-shift only filter tested
  (off-duty officers never appear)
- [ ] Stale location filter tested
  (officers not updated in 5+ min excluded)
- [ ] Already-assigned filter tested
  (officers on another incident excluded)
- [ ] Capability matching tested for all cert types
- [ ] Fit score calculation tested with edge cases
- [ ] Route Calculator integration tested
- [ ] Graceful fallback when Route Calculator is down
- [ ] Indoor incident flag handled correctly
- [ ] Multi-incident exclusion tested
- [ ] Full response under 600ms verified
- [ ] Proximity query log writing correctly
- [ ] Internal API key validation working
- [ ] Read-only access to sod schema confirmed
  (service cannot write to sod schema)

---

## 18. What the Dashboard Panel Shows

The Master Agent structures proximity data into
a dispatch panel the operator sees on the C4I dashboard:

```
┌─────────────────────────────────────────────────────┐
│ 👥 RECOMMENDED OFFICERS — INC-2024-001              │
│ 7 officers on shift · 3 recommended                 │
├─────────────────────────────────────────────────────┤
│ #1  Ahmed Bello          🔫 Armed    ✅ First Aid   │
│     Hotel Lobby · 180m · ETA 1m 21s · Score 94     │
│     [PING AHMED]  [VIEW LOCATION]  [ASSIGN]         │
├─────────────────────────────────────────────────────┤
│ #2  Grace Okonkwo        👊 Unarmed  ✅ First Aid   │
│     Car Park L2 · 420m · ETA 3m 9s · Score 86      │
│     [PING GRACE]  [VIEW LOCATION]  [ASSIGN]         │
├─────────────────────────────────────────────────────┤
│ #3  Emeka Nwosu          🔫 Armed    — No First Aid │
│     Main Gate · 780m · ETA 5m 51s · Score 71       │
│     [PING EMEKA]  [VIEW LOCATION]  [ASSIGN]         │
├─────────────────────────────────────────────────────┤
│ ⚠️  EXCLUDED                                        │
│  Bola Adeyemi — Location stale (12 min ago)        │
│  Tunde Fashola — Already responding to INC-000     │
└─────────────────────────────────────────────────────┘
```

---

*Version 1.0 — Lemtik Security Engineering*
*This service answers one question: who do we send?*
*It runs only when an incident demands it.*
*Speed and accuracy over everything else.*