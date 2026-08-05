-- 002 — keep failed reads out of the published daily index.
--
-- Before this, daily_price_index averaged every snapshot, including rows a
-- failed fetch had written with regular_price = 0.00 and rows validation had
-- already flagged. Those pulled avg_regular below the real price, and Kroger's
-- "no promotion" sentinel of promo = 0 became min(sale_price), pinning the
-- sale line in the per-item charts to $0.
--
-- Source data is untouched: this only rebuilds the derived view and adds
-- indexes. Apply against a live database with:
--     psql "$DATABASE_URL" -f migrations/002_index_excludes_bad_rows.sql

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS daily_price_index;

CREATE MATERIALIZED VIEW daily_price_index AS
SELECT
    p.upc,
    w.product_name,
    date_trunc('day', p.recorded_at) AS day,
    round(avg(p.regular_price), 2)::float8          AS avg_regular,
    round(avg(NULLIF(p.unit_price, 0)), 2)::float8  AS avg_unit,
    round(min(NULLIF(p.sale_price, 0)), 2)::float8  AS best_sale
FROM price_snapshots p
JOIN watchlist w USING (upc)
WHERE p.error IS NULL AND p.regular_price > 0
GROUP BY p.upc, w.product_name, date_trunc('day', p.recorded_at);

-- Required for REFRESH MATERIALIZED VIEW CONCURRENTLY, so the hourly refresh
-- no longer takes an exclusive lock the dashboard has to wait behind.
CREATE UNIQUE INDEX daily_price_index_key ON daily_price_index (upc, day);

-- Backs the per-item "last clean price" lookup in validate.
CREATE INDEX IF NOT EXISTS price_snapshots_clean_recent
    ON price_snapshots (upc, recorded_at DESC)
    WHERE error IS NULL AND regular_price > 0;

COMMIT;
