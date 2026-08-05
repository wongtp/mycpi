-- 003 — OPTIONAL housekeeping. Not required; not applied automatically.
--
-- Migration 002 already excludes these rows from every published number, and
-- src/db.py no longer writes new ones. This script only removes the historical
-- placeholder rows a failed fetch left behind (regular_price = 0.00), for
-- anyone who would rather they not sit in the table at all.
--
-- This DELETES rows. Inspect first:
--     SELECT upc, recorded_at, error FROM price_snapshots WHERE regular_price <= 0;
--
-- Then, if you want them gone:
--     psql "$DATABASE_URL" -f migrations/003_purge_zero_price_rows.sql

BEGIN;

DELETE FROM price_snapshots WHERE regular_price <= 0;

-- Stop the placeholder rows from ever coming back at the schema level.
ALTER TABLE price_snapshots
    ADD CONSTRAINT price_snapshots_regular_price_positive
    CHECK (regular_price > 0);

REFRESH MATERIALIZED VIEW CONCURRENTLY daily_price_index;

COMMIT;
