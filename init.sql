CREATE TABLE watchlist (
    upc VARCHAR(255) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE price_snapshots (
    id BIGSERIAL PRIMARY KEY,
    upc VARCHAR(255) REFERENCES watchlist(upc),
    location_id VARCHAR(255) NOT NULL,
    regular_price NUMERIC(10, 2) NOT NULL,
    unit_price NUMERIC(10, 2),
    sale_price NUMERIC(10, 2),
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    error TEXT,
    UNIQUE (upc, location_id, recorded_at)
);

CREATE TABLE basket_snapshots (
    id BIGSERIAL PRIMARY KEY,
    location_id VARCHAR(255) NOT NULL,
    total_price NUMERIC(10, 2) NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (location_id, recorded_at)
);

-- Only clean rows shape the published index. Flagged snapshots stay in
-- price_snapshots as history, but averaging them in would let one bad read
-- move a day's price. NULLIF drops Kroger's "no promotion" 0 so it can't
-- become the day's best sale price.
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

-- REFRESH MATERIALIZED VIEW CONCURRENTLY requires a unique index; without one
-- the hourly refresh takes an exclusive lock and the dashboard blocks on it.
CREATE UNIQUE INDEX daily_price_index_key ON daily_price_index (upc, day);

-- Validation looks up the last clean price for every basket item each run.
CREATE INDEX price_snapshots_clean_recent
    ON price_snapshots (upc, recorded_at DESC)
    WHERE error IS NULL AND regular_price > 0;

CREATE TABLE bls_cpi (
    series_id   VARCHAR(20),
    year        INT,
    month       INT,          -- 1..12, parsed from 'M01'
    value       NUMERIC(10,3),
    fetched_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (series_id, year, month)
);
