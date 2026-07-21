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

CREATE MATERIALIZED VIEW daily_price_index AS
SELECT
    p.upc,
    w.product_name,
    date_trunc('day', p.recorded_at) AS day,
    round(avg(p.regular_price), 2)::float8 AS avg_regular,
    round(avg(p.unit_price), 2)::float8   AS avg_unit,
    round(min(p.sale_price), 2)::float8   AS best_sale
FROM price_snapshots p
JOIN watchlist w USING (upc)
GROUP BY p.upc, w.product_name, date_trunc('day', p.recorded_at);
