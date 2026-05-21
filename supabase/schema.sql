-- Shif1 UP — Supabase schema
-- Run this in the Supabase SQL Editor before the first ingest.
-- Tables are also auto-created by SupabaseF1Service.initialize() on startup,
-- so this file is provided as a reference and for manual inspection only.

-- -------------------------------------------------------------------------
-- Auth (users)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    preferences     JSONB DEFAULT '{}',
    is_admin        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -------------------------------------------------------------------------
-- F1 historical data
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS drivers (
    driver_id   TEXT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    nationality TEXT,
    number      INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS constructors (
    constructor_id   TEXT PRIMARY KEY,
    constructor_name TEXT NOT NULL,
    nationality      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS races (
    race_id      TEXT PRIMARY KEY,
    year         INTEGER NOT NULL,
    round        INTEGER NOT NULL,
    gp           TEXT NOT NULL,
    date         TEXT,          -- stored as 'YYYY-MM-DD' string
    circuit_name TEXT,
    country      TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS race_results (
    race_id          TEXT    NOT NULL,
    position         INTEGER NOT NULL,
    driver_id        TEXT REFERENCES drivers(driver_id),
    constructor_id   TEXT REFERENCES constructors(constructor_id),
    grid             INTEGER,   -- qualifying/grid position (populated after re-ingest)
    points           FLOAT,
    time             TEXT,
    fastest_lap      BOOLEAN,
    fastest_lap_time TEXT,
    status           TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (race_id, position)
);

CREATE TABLE IF NOT EXISTS laps (
    race_id      TEXT    NOT NULL,
    driver_id    TEXT    NOT NULL,
    lap_number   INTEGER NOT NULL,
    lap_time_ms  INTEGER,
    sector1_ms   INTEGER,
    sector2_ms   INTEGER,
    sector3_ms   INTEGER,
    tyre         TEXT,
    pit          BOOLEAN,
    position     INTEGER,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (race_id, driver_id, lap_number)
);

-- -------------------------------------------------------------------------
-- Indexes for common query patterns
-- -------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_race_results_race_id   ON race_results (race_id);
CREATE INDEX IF NOT EXISTS idx_race_results_driver_id ON race_results (driver_id);
CREATE INDEX IF NOT EXISTS idx_races_year             ON races (year);
CREATE INDEX IF NOT EXISTS idx_laps_race_id           ON laps (race_id);
