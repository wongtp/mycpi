# Household-Basket Price Tracker — Build Plan

A scheduled ETL pipeline that snapshots the current price of your recurring
household basket from the Kroger API, accumulates a price history that doesn't
exist anywhere else, and charts per-item trends plus a whole-basket inflation
index.

**Ground rule for this project:** you write the code, AI reviews it. For each
phase below there's a "pull me in for" note — that's where a design review or a
"why is this wrong" question pays off. Everything else, write first, ask second.

**The one concept that shapes everything:** the API only knows the price *right
now*. There is no history to fetch. The history is a thing *your pipeline
creates* by running repeatedly over days. On day 1 you have one data point.
That's not a bug — it's the whole artifact.

---

## The pipeline at a glance

```
watchlist ─► EXTRACT ─► TRANSFORM ─► VALIDATE ─► LOAD ─► Postgres ─► UI
            (pull each  (clean +     (sanity     (upsert,           (charts)
             product's   compute      checks)     idempotent)
             price)      basket)
```

| Stage | Job | Input | Output |
|---|---|---|---|
| **Extract** | Auth, then fetch current price for each watchlist item at one store | watchlist of product IDs + a location ID | raw JSON per product |
| **Transform** | Parse JSON into clean records; compute the basket total for this run | raw JSON | clean per-item rows + one basket row |
| **Validate** | Reject/flag bad data (nulls, zero/negative, wild jumps, missing items) | clean rows | validated rows + a run report |
| **Load** | Write to Postgres without creating duplicates on re-run | validated rows | rows in `price_snapshots` + `basket_snapshots` |
| **Schedule** | Run the above on a timer so history accumulates | — | growing dataset |
| **Serve** | Query the history and chart it | Postgres | per-item + basket charts |

---

## Phase 0 — Learn the API in Postman (no code yet)

Goal: understand the auth flow and the data shape *before* you write a line of
Python. If you can't get a price in Postman, you can't get one in code.

**Do:**
1. Register an app at https://developer.kroger.com/ → get a `client_id` and
   `client_secret`.
2. Understand the OAuth2 **client-credentials** flow: you POST your client
   credentials to the token endpoint, you get back a **bearer token** that
   expires (short-lived, ~30 min). Every product request carries that token in
   an `Authorization: Bearer …` header.
3. Hit the **Locations API** to get a `locationId` for a store near you (any
   store — it just anchors the prices). Save one ID.
4. Hit the **Products API** with a search term + that `locationId`. Find where
   the price actually lives in the response (look for the `items` array and a
   nested `price` object with regular vs. promo). Note that price is **only
   returned when you pass a locationId**, and some products won't have a price
   at some stores.
5. For each thing you reorder (cat food, coffee, paper towels, skincare), search
   it and record its **productId** (or UPC). That list is your watchlist.

**Decisions you make here:**
- Which store `locationId` to anchor on.
- Which ~8–15 products go in the watchlist (start small).
- Which fields you care about (regular price, promo price, size, name).

**Milestone:** a Postman collection where you can (a) get a token, (b) get a
location, (c) get a product's current price. You can describe the JSON shape
from memory.

**Docs:**
- Portal: https://developer.kroger.com/
- Reference index: https://developer.kroger.com/reference
- Products API: https://developer.kroger.com/reference/api/product-api-public
- Official Postman workspace: https://www.postman.com/kroger/the-kroger-co-s-public-workspace/documentation/ki6utqb/kroger-public-apis

---

## Phase 1 — Extract, minimal: one product, printed

Goal: reproduce the Postman "get one price" flow in Python. Nothing more.

**Project scaffolding** (this is your "how do I start a real project vs a script"
gap — here's the minimum, resist adding more):

```
price-tracker/
├── .env               # secrets: KROGER_CLIENT_ID, KROGER_CLIENT_SECRET
├── .gitignore         # MUST include .env  ← check this before your first commit
├── requirements.txt   # requests, python-dotenv, psycopg[binary]
├── src/
│   ├── kroger_client.py   # auth + fetch (Extract lives here)
│   └── main.py            # orchestrates a run
└── README.md
```

- Use a **virtual environment** (`python -m venv .venv`) so deps are isolated.
- Load secrets from `.env` with `python-dotenv` — never hardcode the client
  secret, never commit it.

**What to implement (your job):**
- `get_token()` → returns a bearer token. For now, fetch a fresh one every run;
  caching comes later.
- `fetch_product(product_id, location_id, token)` → returns the raw JSON.
- In `main.py`: get token → fetch one product → print its current price.

**Guiding questions to answer as you write it:**
- Where does the secret come from, and how do you guarantee it never lands in
  git history?
- What happens if the token request fails or the product has no price at that
  location — does your code crash or handle it?

**Pull me in for:** a review of `kroger_client.py` once it works — token
handling, error handling, and whether the auth belongs where you put it.

**Milestone:** `python src/main.py` prints the live price of one real product.

---

## Phase 2 — Model the data + Postgres round-trip (still one item)

Goal: design your tables, then prove you can write one snapshot to Postgres and
read it back. Do the modeling *before* the code — this is the decision that's
expensive to change later.

**Spin up Postgres locally** with Docker (you already know Docker):
one container, one database. Keep the connection string in `.env`.

**Draft schema — treat this as a starting point to react to, not gospel:**

```sql
-- what you track
watchlist (
  product_id   text PRIMARY KEY,
  name         text,
  size         text,
  category     text
)

-- one row per product per run  ← this is where history accumulates
price_snapshots (
  id            bigserial PRIMARY KEY,
  product_id    text REFERENCES watchlist(product_id),
  location_id   text,
  price_regular numeric,
  price_promo   numeric,
  captured_at   timestamptz,
  UNIQUE (product_id, location_id, captured_at)   -- idempotency guard
)

-- one row per run: the whole-basket total
basket_snapshots (
  id           bigserial PRIMARY KEY,
  location_id  text,
  basket_total numeric,
  item_count   int,
  captured_at  timestamptz,
  UNIQUE (location_id, captured_at)
)
```

**Design decisions to make (and be able to defend):**
- Why split `watchlist` from `price_snapshots` instead of one wide table?
  (Hint: the price changes every run; the product's name/size doesn't.)
- What makes a snapshot a *duplicate*, and which columns enforce that? (The
  `UNIQUE` constraint is your idempotency guarantee — think about whether
  `captured_at` should be the exact timestamp or the run's date.)
- Store price as `numeric`, never `float` — why does money hate floats?
- What index makes "give me the history of product X" fast?

**What to implement (your job):**
- `db.py` with `insert_snapshot(...)` and `get_history(product_id)`.
- Use **parameterized queries** (`%s` placeholders), never string-formatted SQL
  — know why before you write it.

**Pull me in for:** a schema review before you create the tables, and a look at
your first `insert`/`select` for the injection-safety pattern.

**Milestone:** fetch one price → insert it → query it back → print. End to end
through Postgres.

---

## Phase 3 — Full pipeline: the whole watchlist, E→T→V→L as real stages

Goal: generalize from one item to the basket, and split the four stages into
their own modules. This is the phase that makes it a *pipeline* and not a script
— and it's the part that fills the JD gap.

```
src/
├── kroger_client.py   # EXTRACT
├── transform.py       # TRANSFORM
├── validate.py        # VALIDATE
├── db.py              # LOAD (+ reads for the UI)
└── main.py            # orchestrates: extract → transform → validate → load
```

**Extract** — loop the watchlist, fetch each product's raw JSON. One product
failing (not found, no price at this store, timeout) must **not** kill the whole
run. Collect what succeeded; record what didn't.

**Transform** — two things:
1. Map each raw JSON blob → a clean snapshot record (product_id, prices,
   captured_at). Normalize units, handle a missing promo price gracefully.
2. Compute the **basket index**: sum this run's item prices into one
   `basket_snapshots` row. This is pure logic on data you already have, and it's
   your headline feature ("personal inflation tracker"), so build it in now.

**Validate** — run checks *before* load and decide reject-vs-flag for each:
- price is not null and > 0
- price hasn't jumped more than X% from the last known price for that item
  (catch bad data / API glitches — a $5 item at $0.01 or $500 is wrong)
- every watchlist item is either priced or explicitly logged as missing
- Produce a small **run report**: fetched N, valid M, loaded K, failures [...].

**Load** — upsert with `INSERT … ON CONFLICT DO NOTHING` (or `DO UPDATE` if you
decide re-runs should correct a row). This is what makes a double-run harmless.

**Decisions you make here:**
- Reject bad rows outright, or load them with a `flagged` column? (Real
  pipelines usually keep flagged data — you can't analyze what you dropped.)
- What's the right jump threshold before you call a price suspicious?

**Pull me in for:** the module boundaries (is anything in the wrong file?),
whether your run is genuinely idempotent, and your validation thresholds.

**Milestone:** one command runs the full basket through all four stages, prints
a run report, and lands both per-item rows and a basket row in Postgres —
re-running it changes nothing.

---

## Phase 4 — Schedule it (history starts accumulating)

Goal: turn "current price" into "price history" by running Phase 3 on a timer.

- Start with **system cron** (simplest) or a Python scheduler if you'd rather
  keep it in-process. You already run PM2/cron-style jobs on your Mac mini —
  same idea.
- Run **hourly at first** to fill your charts with visible points fast (grocery
  prices barely move hourly, but it proves the mechanism), then dial back to
  **daily** once you have depth.
- Idempotency (Phase 3) is what makes scheduling safe: an overlapping or
  double-fired run can't corrupt anything.
- **Log every run** — items fetched, validated, loaded, failures, duration.
  This is your SRE/observability wheelhouse; lean into it. It's also the thing
  that lets you answer "how do you know it's working?" in an interview.

**Seed for the demo:** while real history builds, insert a handful of clearly
labeled **synthetic** rows so the UI has something to chart on day 1. They're
scaffolding — delete them once real data has accrued. Never let them masquerade
as real.

**Pull me in for:** whether your scheduled job is safe to run unattended
(what happens on failure, on a dead token, on a network blip).

**Milestone:** the job runs on a schedule without you, and the history table
grows on its own.

---

## Phase 5 — Visualize it

Goal: a simple UI showing per-item price history and the basket index over time.

- **Recommended for the prototype: Streamlit.** It's Python-native, needs zero
  frontend experience, and turns "query Postgres → line chart" into a few lines.
  A dropdown to pick a product, a line chart of its history, and a second chart
  for the basket index is a complete, demoable app.
- Simpler still if you want: matplotlib static charts, no web at all.
- **Resume-upgrade path (later):** a small **FastAPI** endpoint serving the
  history as JSON + a **React** frontend charting it. This is more work, but it
  directly hits the JD's REST-API and React gaps. Do it as a Phase 5.5 once the
  Streamlit version works — don't block the prototype on learning React.

**Features worth having:**
- Per-item price history line chart.
- Whole-basket index over time (your headline).
- Optional: highlight where an item dropped below a buy threshold you set.

**Milestone:** you can open a page, pick an item, and see its price history +ish
the basket trend.

---

## Phase 6 — AWS + Terraform (the resume multiplier, do last)

Only after the whole thing works locally. This is a near-mechanical port, and
it's what turns "a price tracker" into "a scheduled data pipeline I built and
deployed on AWS with infrastructure-as-code" — the sentence that answers the
JD's biggest gap.

- **RDS** — swap local Postgres for managed Postgres (change the connection
  string, mostly).
- **Lambda + EventBridge** — run the snapshot job in the cloud on a schedule
  instead of local cron.
- **S3** — optionally archive each run's raw JSON pulls (your "data lake").
- **Terraform** — provision RDS + Lambda + EventBridge + S3 + IAM as code
  instead of clicking the console. Doing this instead of console-clicking is
  what fills the "IaC beyond Ansible" gap.

Keep everything tiny and tear it down when idle — this fits in AWS free tier if
you're disciplined about instance sizes.

**Pull me in for:** the Terraform structure and IAM permissions before you apply
anything (IAM is the easiest place to accidentally over-permission).

---

## How the phases map to the JD

| JD requirement | Phase that covers it |
|---|---|
| Strong Python | 1–5, this is the whole thing |
| Data pipelines (ingestion, transformation, validation, publishing) | 3 |
| PostgreSQL, data models, SQL | 2–3 |
| ETL/ELT | 3–4 |
| Data-quality validation | 3 (validate stage) |
| REST APIs | 5.5 (FastAPI) |
| React | 5.5 (frontend) |
| AWS / distributed | 6 (RDS, Lambda, S3) |
| IaC beyond Ansible (Terraform) | 6 |
| Observability / reliability | 4 (run logging — your strength) |

A working prototype is Phases 0–5. Phases 5.5 and 6 are what make it
interview-loud, and they're additive, so you can submit the app whenever the
prototype is defensible and keep building.

---

## Your immediate next three actions

1. Register the Kroger app and get your `client_id` / `client_secret`.
2. In Postman: get a token → get a `locationId` → pull one product's price.
   Stare at the JSON until you know exactly where the price lives.
3. Write down your ~10-item watchlist with each product's ID.

Then start Phase 1. Ping me for the `kroger_client.py` review when Extract works.
