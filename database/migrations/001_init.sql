CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
SET search_path TO public, extensions;

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  display_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS queue_lengths (
  id SERIAL PRIMARY KEY,
  description TEXT NOT NULL UNIQUE,
  colour TEXT NOT NULL,
  sort_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hospitals (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  last_inspected DATE NOT NULL,
  location GEOMETRY(Point, 4326) NOT NULL,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
  id SERIAL PRIMARY KEY,
  hospital_id INTEGER NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  queue_length_id INTEGER NOT NULL REFERENCES queue_lengths(id),
  cleanliness TEXT NOT NULL CHECK (length(cleanliness) BETWEEN 1 AND 500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS hospitals_location_gix ON hospitals USING GIST (location);
CREATE INDEX IF NOT EXISTS reports_hospital_created_idx
  ON reports (hospital_id, created_at DESC);
CREATE INDEX IF NOT EXISTS reports_user_idx ON reports (user_id);

CREATE OR REPLACE VIEW hospital_report_details AS
SELECT
  r.id,
  r.hospital_id,
  h.name AS hospital_name,
  h.location,
  r.user_id,
  u.display_name AS contributor_name,
  r.queue_length_id,
  q.description AS queue_description,
  q.colour AS queue_colour,
  r.cleanliness,
  r.created_at
FROM reports r
JOIN hospitals h ON h.id = r.hospital_id
JOIN users u ON u.id = r.user_id
JOIN queue_lengths q ON q.id = r.queue_length_id;

CREATE OR REPLACE VIEW hospital_latest_status AS
SELECT
  h.id,
  h.name,
  h.last_inspected,
  h.location,
  h.user_id,
  COALESCE(latest.queue_length_id, unknown_queue.id) AS queue_length_id,
  COALESCE(latest.queue_description, unknown_queue.description) AS queue_description,
  COALESCE(latest.queue_colour, unknown_queue.colour) AS queue_colour,
  COALESCE(latest.cleanliness, 'No report yet') AS cleanliness,
  latest.created_at AS latest_report_at
FROM hospitals h
CROSS JOIN LATERAL (
  SELECT id, description, colour
  FROM queue_lengths
  WHERE description = 'Unknown'
) unknown_queue
LEFT JOIN LATERAL (
  SELECT
    r.queue_length_id,
    q.description AS queue_description,
    q.colour AS queue_colour,
    r.cleanliness,
    r.created_at
  FROM reports r
  JOIN queue_lengths q ON q.id = r.queue_length_id
  WHERE r.hospital_id = h.id
  ORDER BY r.created_at DESC, r.id DESC
  LIMIT 1
) latest ON TRUE;
