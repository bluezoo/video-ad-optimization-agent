# Demo Scenario — Connected mode (live BlueZoo, workstream 11b)

Scenario file for the `demo-scenario-verifier` subagent (see `.claude/agents/`),
driven through a local `make dev` instance (adk web, port 8501) via
chrome-devtools MCP. Modeled on `docs/demo-scenarios/fashion.md`'s Act/Scene
shape. Covers Phase 11b: `LiveBlueZooAudienceDataSource`
(`app/audience/live_bluezoo.py`), the connected-mode conformer against
BlueZoo's real MO_92 Data Warehouse, reached through the 11a
`AudienceDataSource` seam when `APP_MODE=connected`.

**Cost note:** every scene here is read-only against BlueZoo, and cheap. Each
scene's `run_query` scans at most a 30-day window × ≤3 sensors × ~41 bytes/row
≈ 350 KB — against BlueZoo's 500 GB/sensor-location monthly allowance. Running
every scene in this file end to end does not meaningfully dent that budget.

## Setup (all scenes)

Prereqs: `app/.env` configured with `BLUEZOO_BASE_URL` and
`BLUEZOO_ACCESS_KEY` (the cluster-scoped MO_92 pair — never write their values
into this file or any other tracked doc; they live only in the gitignored
`app/.env`). Demo DB present (`make dev` populates it on first run).

**The sensor map.** Campaign 1's screen roster is `[101, 102, 103]`
(`python3 -c "from app.demo_data.attribution import screens_for_campaign;
print(screens_for_campaign(1))"`). Map those three screens onto the three
BlueZoo sensors verified in Task 6 Step 0 as real, currently-valid,
full-coverage producers:

```
BLUEZOO_SENSOR_MAP=101:77,102:80,103:89
```

**Why these sensors** (provenance: `tests/unit/data/bluezoo_sensor_visits_sample.md`,
quoted): "sensors 77, 80 chosen as the top valid-row producers over
2026-07-19..2026-07-26 (counts: 672, 672 — tied with several other sensors at
full 96-slot/day coverage for all 7 days; 77 and 80 are the first two in the
server's descending-order result for that tie group)." 89 is the next sensor
in that same tied, full-coverage group (`77, 80, 89, 342, 865, ...` all
`n=672`). Selection query (Step 0):

```sql
select sensor_id, count(*) as n from sensor_visits
where timestamp >= '2026-07-19' and timestamp < '2026-07-26' and valid
group by sensor_id order by n desc
```

The owner condition this satisfies: "sensors chosen from verified recent
valid rows, so a scene failure means code, not a dark or never-commissioned
sensor" — MO_92's recent grid coverage is only ~34% and 19 live sensors are
`valid=false`, so an unverified sensor id would fail these scenes for data
reasons that look like code bugs.

Launch commands per scene are given below; all of them run from the repo
root and start with `APP_MODE=connected`.

## Scene 1 — fail-closed (no BlueZoo config)

> **Amended (workstream 11b, 2026-07-28):** Scene 1 originally asserted a
> tool-time error; live verification showed startup demo-seeding reaches the
> audience seam first, so misconfigured connected mode fail-fasts at `make
> dev` startup — a stronger fail-closed surface.

**Launch (explicit empty overrides — required):**

```bash
APP_MODE=connected BLUEZOO_BASE_URL= BLUEZOO_ACCESS_KEY= make dev
```

Do not rely on merely leaving `BLUEZOO_*` unexported: `app/.env` is
auto-loaded by the `demo-assets`/dev tooling in a way that fills in unset
variables, so a shell that "never exported them" can still end up
BlueZoo-configured if `app/.env` sets them. Explicit empty-string overrides
on the command line are what guarantees "missing" per the constructor's
`.strip()` check (an empty string strips to empty, which counts as missing).

**What actually happens:** `make dev` depends on the `demo-assets` target,
which runs `python -m scripts.demo_assets`. That script's first import
(`from app.config import LOCAL_ASSETS_DIR`) pulls in the `app` package,
whose `app/agent.py` runs `init_database()` + `seed_demo_data()` at **module
import time** — unconditionally, every launch. Seeding derives the seeded
demo campaigns' metrics through the audience-data seam
(`get_audience_datasource()`), which resolves to
`LiveBlueZooAudienceDataSource()` under `APP_MODE=connected`; its constructor
raises immediately because `BLUEZOO_BASE_URL`/`BLUEZOO_ACCESS_KEY` are
missing. The exception propagates out of the import, `demo-assets` exits
non-zero, and `make` aborts the `dev` target **before `adk web` ever runs** —
**no query is ever sent, no tool call ever fires, and port 8501 never
binds.**

**Expected error** (`BlueZooConfigError` from `app/audience/live_bluezoo.py`,
exact message fragments to look for in the terminal/startup log):

- `"APP_MODE=connected requires BLUEZOO_BASE_URL and BLUEZOO_ACCESS_KEY"`
- `"cluster-scoped pair"`
- `"SETUP_INSTRUCTIONS.md"`

Also expect the wrapping context from `app/agent.py`'s import-time try/except:
`"[Agent Init] Database initialization error: ..."` and
`"[Agent Init] DB_PATH attempted: ..."` printed to stderr, then a Python
traceback ending in `app.audience.live_bluezoo.BlueZooConfigError: ...`, and
finally `make: *** [demo-assets] Error 1`.

**Pass criteria:** the three error fragments above appear in the startup
log; the process exits non-zero and port 8501 never binds (no `adk web`
banner, nothing reachable at `http://localhost:8501`); `campaigns.db` is
unchanged by this run — no new metrics rows — no silent fallback to demo
data.

**Fail criteria:** the server starts and binds port 8501 despite missing
BlueZoo config, or any metrics rows appear — either means a silent fallback
to demo data survived, which is the exact regression this workstream's
fail-closed design prevents.

## Scene 2 — happy path (real MO_92 rows)

**Launch:**

```bash
APP_MODE=connected BLUEZOO_SENSOR_MAP=101:77,102:80,103:89 make dev
```

(`BLUEZOO_BASE_URL`/`BLUEZOO_ACCESS_KEY` come from `app/.env` — do not
re-specify them on the command line or anywhere else in this doc.)

**Query 1:** "Show me the pending videos for campaign 1, then activate the
first one." (same setup-video insert as Scene 1 if needed, using a fresh
`video_filename` so it doesn't collide with any earlier scene's row.)

**Query 2 (follow-up turn):** "Show me that video's campaign metrics."

**Expected tool calls:**

- Query 1: `list_pending_videos`, then `activate_video` (the review/
  activation tool).
- Query 2: `get_campaign_metrics` (or `get_top_performing_ads` /
  `get_campaign_insights` for the same campaign — any of these surfaces
  impressions for the activated video).

**Expected response:** the activation succeeds and reports
`metrics_generated` > 0; the metrics query reports non-zero impressions for
campaign 1.

**Evidence the data is LIVE (check all three; (a) is the pass gate, (b) and
(c) corroborate):**

- **(a) Server log** — the terminal running `make dev` prints a line of the
  exact shape:

  ```
  bluezoo live read: policy=valid-only sensors=[77, 80, 89] window=<from>..<to> rows=<n>
  ```

  (logger `app.audience.live_bluezoo`) with `rows=` > 0. This is the pass
  gate: if this line is absent, the read did not reach BlueZoo at all.
- **(b) Numbers differ from demo mode** — the reported impressions for this
  video are NOT the deterministic synthetic values a `make dev` run under
  `APP_MODE=demo` (or unset) would report for the same video/campaign,
  because they derive from real BlueZoo float interval counts joined through
  attribution, not the seeded synthetic generator.
- **(c) No error anywhere in the trace.**

**Fail criteria:** the log line is missing or shows `rows=0` for a window
that should have data, any exception in the trace, or numbers that exactly
match the demo-mode deterministic values (would indicate the connected path
silently fell through to the synthetic source).

## Scene 3 — policy knob (`BLUEZOO_VALID_POLICY=include-all`)

**Launch:**

```bash
APP_MODE=connected BLUEZOO_SENSOR_MAP=101:77,102:80,103:89 BLUEZOO_VALID_POLICY=include-all make dev
```

**Query:** repeat a metrics-affecting action from Scene 2 — e.g. "Activate
[another pending video for campaign 1] and show me the campaign's metrics"
(insert another synthetic pending video first, same pattern as Scenes 1–2, or
re-run `generate_additional_metrics` for the video from Scene 2 if it's
already activated).

**Expected tool calls:** same shape as Scene 2 (activation and/or metrics
tool).

**Expected server log:**

```
bluezoo live read: policy=include-all sensors=[77, 80, 89] window=<from>..<to> rows=<n>
```

— note `policy=include-all` in place of `policy=valid-only`. Since sensors
77/80/89 were selected precisely because they have no `valid=false` rows in
the verified capture window, this scene is checking that the knob is wired
end to end (the SQL drops its `and valid` clause and the log reflects the
active policy), not asserting a metric delta — `rows=` may legitimately be
identical to Scene 2's for these particular sensors.

**Pass criteria:** the log line shows `policy=include-all`; no error in the
trace.

**Fail criteria:** the log line still shows `policy=valid-only` (the env var
isn't being read), or any error.
