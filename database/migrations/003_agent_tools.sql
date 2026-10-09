ALTER TABLE reports ADD COLUMN IF NOT EXISTS cleanliness_score DOUBLE PRECISION
  CHECK (cleanliness_score >= 1 AND cleanliness_score <= 5);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS queue_wait_minutes DOUBLE PRECISION
  CHECK (queue_wait_minutes >= 0 AND queue_wait_minutes <= 1440);
CREATE INDEX IF NOT EXISTS hospitals_geography_gix ON hospitals USING GIST ((location::geography));
