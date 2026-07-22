# mycpi — Personal CPI / Household Basket Price Tracker

[![CI](https://github.com/wongtp/mycpi/actions/workflows/ci.yml/badge.svg)](https://github.com/wongtp/mycpi/actions/workflows/ci.yml)

**Current:** A scheduled ETL pipeline that snapshots the current price of your recurring household basket from the Kroger API, accumulates a price history that doesn't exist anywhere else, and charts per-item trends plus a whole-basket inflation index.

**End goal:** Personal CPI index with a UI designed to track personal household spending and costs including groceries, rent, gas, utilities, and more.

The key idea: the Kroger API only knows the price *right now* — there is no history to fetch. The history is something this pipeline *creates* by running on a schedule, one snapshot at a time.

## Pipeline

```
watchlist → extract → transform → validate → load → Postgres → (UI, Phase 5)
```

Each run prices every item in `productList.txt` at one store, computes the whole-basket total, flags (never drops) bad rows, and upserts idempotently so re-runs can't create duplicates.

## Prerequisites

- Python 3.11+
- Docker (for the Postgres database)
- A Kroger developer account (`client_id` + `client_secret`) — https://developer.kroger.com/

## Setup

1. **Create and activate a virtual environment, then install dependencies:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure secrets.** Copy the example and fill in your values:

   ```bash
   cp .env.example .env
   # edit .env: Kroger credentials + Postgres connection details
   ```

3. **Start the database.** This launches Postgres and runs `init.sql` to create the tables (only on a fresh volume):

   ```bash
   docker compose up -d
   ```

## Running a snapshot

Run from the **project root** (the path anchoring in the code depends on it):

```bash
python src/main.py
```

A clean run exits `0` and prints a per-item report plus the basket total; a run with any missing/flagged item exits non-zero and skips the basket snapshot (so the index only ever records a complete basket).

## Scheduling (accumulate history)

History accumulates by running the snapshot on a timer. With system cron, add a line via `crontab -e` using **absolute paths** (cron runs with a bare environment):

```cron
0 * * * * cd /path/to/mycpi && /path/to/mycpi/.venv/bin/python src/main.py >> /path/to/mycpi/cron.log 2>&1
```

The hourly schedule fills the history; output is appended to `cron.log`. Idempotent upserts make overlapping or repeated runs safe.

## Tests

Unit tests cover the pure pipeline stages (transform, validate) with no DB or
network — the validate tests monkeypatch the last-price lookup. Run them with:

```bash
pip install -r requirements-dev.txt
pytest
```

CI (`.github/workflows/ci.yml`) runs the suite on every push and PR to `main`.

## Schema migrations

`init.sql` only runs against an *empty* Docker volume, so schema changes after the DB exists must be applied by hand against the live database (see `migrate_recorded_at_timestamptz.sql` for an example).
