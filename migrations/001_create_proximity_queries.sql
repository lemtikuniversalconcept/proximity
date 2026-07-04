CREATE SCHEMA IF NOT EXISTS services;

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
);
