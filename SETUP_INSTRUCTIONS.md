# Setup Instructions

`README.md` is the client-facing overview and is kept stable on purpose — this file is where local dev/setup steps live instead, and it's expected to grow as Version 2 workstreams land (new env vars, new modes, new external accounts). See `.docs/version2-plan/` for what's actually changing and why; see `DEPLOYMENT.md` for Cloud Run / Agent Engine deployment specifics.

## Prerequisites

- Python (a version compatible with `google-adk` — see `app/requirements.txt`; Agent Engine deploys specifically need 3.9–3.13, not 3.14+)
- `make`
- A Google Cloud project (Vertex AI path) or a Google AI Studio API key (AI Studio path) — see Environment below
- Optional: a Google Maps API key for the maps tools (tests/tools degrade gracefully without it)
- For Claude Code development on this repo: `jq` (used by the tracked `.claude/settings.json` PostToolUse hook that auto-runs `make test-unit`) and Node.js/`npx` (used by the chrome-devtools MCP server — see "MCP servers" below)

## Install

```bash
make install        # creates .venv, installs app/requirements.txt
```

**Note (workstream 05):** numpy (`>=1.26.0`) is now a direct dependency for deterministic demo-data generation; after pulling, existing environments need `make install` (or `pip install "numpy>=1.26.0"`) to update.

## Environment

Create `app/.env` with one of:

**Vertex AI path:**
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=<your-project-id>
GOOGLE_CLOUD_LOCATION=global   # required for Gemini 3 / Veo 3.1 models this repo uses
GCS_BUCKET=<your-bucket-name>
```

**AI Studio path:**
```
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=<your-api-key>
GCS_BUCKET=<your-bucket-name>
```

**Optional:**
```
GOOGLE_MAPS_API_KEY=<your-maps-key>   # or MAPS_API_KEY
APP_MODE=demo                          # or connected; default demo — inert until Phase 11/12
BLUEZOO_ACCESS_KEY=<uuid>              # only for scripts/bluezoo_probe.py — see below
BLUEZOO_BASE_URL=<cluster-dwh-url>     # only for scripts/bluezoo_probe.py — see below
```

## BlueZoo schema probe (`scripts/bluezoo_probe.py`)

A read-only tool for answering "what does this BlueZoo tenant's warehouse
actually look like?" — not part of the app, and not needed to run or test it.
No BlueZoo integration code exists yet (that's Phase 11b); this exists so the
adapter can be built against a real schema rather than the published docs alone.

```bash
python scripts/bluezoo_probe.py --out <dir>   # writes scan.json + scan.md
python scripts/bluezoo_probe.py               # markdown digest to stdout
```

- **`BLUEZOO_ACCESS_KEY`** (required) — from the BlueZoo dashboard's Profile
  screen. Read from the environment first, else `app/.env`. Never commit it; the
  script never prints or persists it.
- **`BLUEZOO_BASE_URL`** (optional) — defaults to the Apollo cluster's Data
  Warehouse endpoint. **Hostnames are cluster-scoped, not global:** a key from
  one cluster returns `BAD_TOKEN` against another's host, which reads like a bad
  credential. The Profile screen names your cluster; override this when probing
  a different customer. `--base-url` does the same thing per-invocation.

Read-only by construction: `list_tables`, `desc_table`, and SELECT-only counts,
with non-SELECT statements refused client-side before transmission.

### Cost — read before running any query of your own

**BlueZoo meters a monthly bytes-scanned allowance** (BigQuery style),
undocumented. It exists to prevent abuse, not to bill you, and the ceiling is
per-tenant configuration BlueZoo will raise on request — MO_92 currently sits
at **500 GB per sensor location** per month. But the *default* is low enough to
trip by accident: roughly **735 MB of full-history aggregate queries exhausted
a real tenant's month** at the original 1 GB/sensor-location setting, after
which *every* `run_query` failed — including single-sensor, single-day ones —
until BlueZoo reset it. There is **no endpoint to check remaining
consumption**; you find the limit by hitting it. `list_tables`, `desc_table`
and the Real-time API are exempt.

Practical rules — cheap to follow, and they keep you clear of the wall
regardless of where it currently sits:

- **Never `select *`.** `sensor_dwell` is 120 columns / ~1 KB per row; a full
  scan is ~5 GB in one statement.
- **Name columns explicitly and keep time windows narrow.** The probe counts
  over the last 30 days by default for this reason; `--full-history` is an
  explicit opt-in and is only safe on a tenant known to be empty.
- The probe prints a `COST NOTE` naming the widest table, records
  `select_star_bytes_per_row` in `scan.json`, and raises a distinct
  `QuotaExceeded` (exit code 2) rather than a generic failure.
- **If you do hit it, ask** — BlueZoo raises the limit on request rather than
  making you wait for the month to roll over.

### Saved scans

- `working-docs/bluezoo-live-verification/scan/` — **AP_599** (Apollo, org
  "Walmart Demo"): empty tenant; proves schema and entitlements.
- `working-docs/bluezoo-live-verification/scan-mo92/` — **MO_92** (Morpheus
  *staging*, a hospitality-sector tenant): 5.1M rows of **real customer venue
  data**. Its AccessKey and any extract are customer-confidential; the
  committed artifacts are schema and row counts only — no venue names, no
  traffic rows. Keep it that way: never commit a key, a venue name or a data
  extract from this tenant.

Each cluster issues its **own** AccessKey — an Apollo key returns `BAD_TOKEN`
against the Morpheus host. Findings for both:
`.docs/version2-plan/working-docs/bluezoo-live-verification/findings.md`.

## Run locally

```bash
make dev            # ADK web UI on :8501 (alias: make playground)
```

Open the printed local URL. `make reset-db` wipes `campaigns.db` and repopulates demo data on the next `make dev`.

## Metrics glossary

`docs/METRICS.md` is the single source of truth for what every metric means (impressions, RPI, revenue, circulation, dwell time), aligned to BlueZoo's own vocabulary — read it before touching any metric-related code. It supersedes the metric explanations scattered through code comments and the README's marketing prose; where they disagree, `docs/METRICS.md` wins. (README.md itself stays untouched per this file's header note.)

## Test

**Tier map (workstream 16, 2026-07-23):**

```bash
make test-unit         # tests/unit, ~4s, no LLM calls — fastest feedback loop
make test-e2e           # tests/e2e workflow tests, ~1s, no LLM calls
make test               # unit + e2e (default now — fast, zero LLM calls, seconds)
make test-integration   # tests/integration only (real LLM, agent-routing evals) — targeted subset of the live tier, NOT part of `make test`
make test-live          # LIVE tier: tests/integration + tests/live against real Vertex/Veo/image-gen APIs — see "Live tier" below
make test-live-report   # agents-cli grade/compare reporting layer over live eval traces — INFORMATIONAL, not a gate
make test-all            # everything, including slow Veo tests, ~10+ min
make test-coverage       # pytest --cov=app, HTML report in htmlcov/
```

`make test` used to run unit + integration by default; as of workstream 16 integration moved out of the default target (it needs a real LLM and minutes per run) and now lives under `make test-live` alongside the new `tests/live` media/judge tests. `make test` is fast-by-default again: unit + e2e, seconds, zero network calls.

Run a single test: `pytest tests/unit/test_campaign_tools.py::TestClass::test_name -v`.

**Test isolation note:** Prior to the database late-binding fix (workstream version_2_bug-fixes-and-cleanup), unit tests leaked writes into the real `campaigns.db` because `DB_PATH` was bound at import time, preventing test fixtures from patching it. Older checkouts with accumulated junk campaigns should run `make reset-db` once to clear them. The fix ensures all tests use isolated temporary database copies.

**`make test-integration` and `make test-live` require the ADK eval extra:** `pip install "google-adk[eval]==2.5.0"` (into `.venv`) — this extra is **not** in `app/requirements.txt` (deliberately; it pulls pandas/tabulate/rouge-score, which the fast tier never needs). Without it, `AgentEvaluator`/`LocalEvalService` imports raise a *lazy* ImportError that older test-suite code paths could silently convert into "not available" skips. (Found during workstream 01; the over-broad catch itself is Phase 2, item 7 — workstream 16's `tests/integration/eval_harness.py` fails loudly instead, see CLAUDE.md's Gotchas.) Both targets also need `app/.env` present with real credentials (real LLM/Veo/image-model calls); `make test-live` checks for the file and exits with an error if it's missing.

### Live tier (`make test-live`) — workstream 16

`make test-live` runs `pytest tests/integration tests/live` against real Vertex AI (agent routing evals, Veo video generation, image generation, and a Gemini-multimodal judge that reviews generated media against a rubric). This is the tier that closes `99-open-questions.md` Q19: fast tests prove nothing about actual model behavior, so a second, honest, real-money tier exists specifically to catch routing/prompt/media regressions that only show up against the live LLM.

**Setup:**
- `app/.env` with a working Vertex AI (or AI Studio) config — see "Environment" above. `make test-live` guards on this file's presence and exits with an error if it's missing.
- `pip install "google-adk[eval]==2.5.0"` into `.venv` (see above) — required for the eval harness's `LocalEvalService`/`local_eval_sets_manager` imports.
- Local-first storage: leave `GCS_BUCKET` unset in `app/.env` for the live tier. It is force-unset for the duration of the run either way (no `storage.googleapis.com` URLs anywhere in a live test's output) — the ws16 resolution of the phase doc's storage-policy open item is local-first, no exceptions.

**Cost and runtime (owner-approved, 2026-07-23): cost is accepted, correctness comes first.** A full clean run: **26 passed / 0 failed in ~674s (11m13s)** — real Gemini routing calls across 5 agent eval sets, 2 full Veo two-stage media pipelines (image + video), 1 from-scratch onboarding image generation, and ~6 Gemini-judge multimodal review calls (5 media + 1 chart). Expect real Vertex/Veo/image-model billing on every run.

**Flakiness watchlist (observed during workstream 16 — none of these indicate a regression by themselves; rerun before escalating):**
- **Transient Vertex `400 INVALID_ARGUMENT`** on routing calls — roughly 1 per full run. This correctly **fails** the case (not vacuously); a clean immediate rerun has been the consistent outcome.
- **LLM-judge nondeterminism** on the answer-dimension eval scoring and on media hard-checks — mitigated by two bounded, owner-approved one-shot retries in `tests/integration/eval_harness.py` (answer re-judge, GATE 3) and `tests/live/judge.py` (media hard-check re-judge, GATE 4); each retries exactly once and prints/`warnings.warn`s loudly when it fires, so a masked flake is always visible in the test output.
- **Transient Veo generation error** ("operation completed after ~20s, returned no result" — abnormally fast, no video produced) — a live-infra hiccup, not a code defect; rerun the affected test.
- **Media re-judge tradeoff (owner-approved, GATE 4):** retrying a hard-check failure once lowers the odds of *catching* a genuinely BORDERLINE policy violation (probability of detection goes from `p` to `p²` across two independent judge calls). Unambiguous violations are unaffected — the negative-control fixtures (rendered-text overlay, wrong-subject-for-archetype) fail **both** judge calls and the test still fails as expected.

See `.docs/version2-plan/working-docs/16-live-api-testing/WORK_LOG.md` for the full OWNER GATE 1–4 decision record and `.docs/version2-plan/16-live-api-testing.md` for the phase's design.

**Flakiness watchlist addendum (workstream 11b):** `tests/live/test_live_bluezoo_datasource.py` assumes MO_92 sensors 77 and 80 are currently reporting (evidence: `tests/unit/data/bluezoo_sensor_visits_sample.md`) — if both go dark the non-empty assertions fail; swap the ids in that test's `BLUEZOO_SENSOR_MAP` monkeypatch (and, if you're pointing at a different tenant, in the connected-mode `BLUEZOO_SENSOR_MAP` below) rather than treating it as a regression.

**Flakiness watchlist addendum (workstream 14c):** `tests/live/test_omni_video_edit.py` requires a real, already-generated demo video asset on disk (`generated/blue-floral-maxi-dress-122025-asian-beach-romantic.mp4`, the first `REAL_VIDEOS` entry in `app/database/mock_data.py`) with a matching `campaign_videos` DB row — a fresh worktree/clean-checkout without generated demo assets will fail this test with a file-not-found error rather than a graceful skip. Run `make dev` once first (repopulates demo data) and ensure the corresponding video file exists under the local assets root before running `make test-live`, or regenerate it via the standard Veo pipeline. Gemini Omni Flash itself is **Preview** on Vertex AI (GA release 2026-06-30, retirement 2027-06-30) — expect this test to need a model-id update or re-verification before that date.

## Connected mode (`APP_MODE=connected`) — live BlueZoo adapter

Phase 11b's live conformer (`app/audience/live_bluezoo.py`) reads real audience
data from BlueZoo's REST Data Warehouse (`run_query` against `sensor_visits`)
instead of the demo-mode SQLite mock. It is a fixed, read-only, one-query
adapter — no query builder, no pagination, no capability probing (see the
module docstring for the full conforming-rules list).

| Variable | Required | Meaning |
|---|---|---|
| `APP_MODE` | yes (`connected`) | Selects the live BlueZoo audience source (Phase 11b). |
| `BLUEZOO_BASE_URL` | yes | Cluster-specific DWH URL, e.g. `https://<cluster-host>/v2/dwh`. **No default** — cluster-scoped, pairs with the key. |
| `BLUEZOO_ACCESS_KEY` | yes | Bare AccessKey UUID (dashboard → Profile). The adapter adds the `AccessKey ` prefix itself. Never commit it. |
| `BLUEZOO_SENSOR_MAP` | yes | `screen_id:sensor_id,...` e.g. `101:77,102:80`. One-to-one; malformed values fail closed at startup. Phase 12's CMS integration decides the long-term source of this mapping. |
| `BLUEZOO_VALID_POLICY` | no (default `valid-only`) | `valid-only` = Rule R (count only commissioning-accepted rows; OUR recommendation, pending BlueZoo confirmation — see `docs/METRICS.md`). `include-all` = no filter. Every live read logs `policy=... rows=...`. |

**The pair rule:** secrets hold a `{base_url, access_key}` pair per tenant,
never a lone key — the base URL is cluster-scoped configuration that travels
with the credential; separating them is how "wrong host" becomes a support
ticket reading "auth is broken" (Phase 13 amendment). Store and inject
`BLUEZOO_BASE_URL` and `BLUEZOO_ACCESS_KEY` together, from the same secret
prefix, for the same tenant — never mix a base URL from one cluster with a
key from another.

**Deploy (Cloud Run)** — one secret per half of the pair, same tenant prefix
so they can't be mixed; note the `^@^` delimiter on `--set-env-vars` because
`BLUEZOO_SENSOR_MAP` itself contains commas:

```bash
# One secret per half of the pair, same tenant prefix so they can't be mixed:
gcloud secrets create bluezoo-morpheus-base-url   --data-file=- <<< "https://<cluster-host>/v2/dwh"
gcloud secrets create bluezoo-morpheus-access-key --data-file=- <<< "<ACCESS_KEY_UUID>"

gcloud run deploy video-ad-agent \
  --set-secrets "BLUEZOO_BASE_URL=bluezoo-morpheus-base-url:latest,BLUEZOO_ACCESS_KEY=bluezoo-morpheus-access-key:latest" \
  --set-env-vars "^@^APP_MODE=connected@BLUEZOO_SENSOR_MAP=101:77,102:80@BLUEZOO_VALID_POLICY=valid-only"
```

Agent Engine deploys inject the same pair through the deploy script's env
config; in-code Secret Manager SDK reads are deliberately Phase 13 Tier B.

**Operational notes:**
- Missing `BLUEZOO_BASE_URL` or `BLUEZOO_ACCESS_KEY` at startup raises
  `BlueZooConfigError` naming exactly which var(s) are missing.
- A rejected credential (`BAD_TOKEN` from BlueZoo) also raises
  `BlueZooConfigError`, naming the `{base_url, access_key}` pair as the thing
  to check — cluster-scoped keys return `BAD_TOKEN` against any other
  cluster's host, which reads like a bad credential but usually isn't one.
- Quota exhaustion (monthly bytes-scanned allowance) raises the distinct,
  **non-retryable** `BlueZooQuotaExceeded` — every `run_query` fails until it
  resets or BlueZoo raises the allowance; the remediation is to ask BlueZoo to
  raise it, not to retry.
- Zero rows is a legitimate result, not an error (fail-closed applies to
  configuration, never to data).
- `BLUEZOO_VALID_POLICY` (and the row count it produced) is logged on every
  live read, so the active policy is always auditable per query.
- **Misconfigured connected mode fails at process startup, not first query.**
  `app/agent.py` runs demo-data seeding at **module import time**
  (unconditionally, every launch), and seeding derives metrics through the
  audience-data seam — so a bad deploy with missing/wrong
  `BLUEZOO_BASE_URL`/`BLUEZOO_ACCESS_KEY` dies immediately at startup
  (`make dev`'s `demo-assets` prerequisite, or the equivalent import in a
  deployed process) instead of surfacing the error later at the first live
  query. This is stronger fail-closed behavior than a lazily-triggered error
  would be, but it also means a misconfiguration is a hard outage, not a
  degraded feature — get the `{base_url, access_key}` pair right before
  deploying.
- **Every connected-mode startup scans BlueZoo, read-only — not just the
  first boot.** Demo-data seeding's metrics regeneration step
  (`app/database/mock_data.py`, "Step 4") runs **unconditionally on every
  `populate_mock_data()` call** — fresh DB or not — regenerating all active
  demo campaigns' metrics through the **live** source rather than the
  synthetic generator. Cost per startup: a few hundred KB of `run_query`
  bytes scanned per campaign window (30-day window × mapped sensors ×
  ~41 B/row), well under BlueZoo's 500 GB/sensor-location monthly allowance,
  but it recurs on every `make dev` restart and every deployed-process
  (re)start while `APP_MODE=connected` and demo campaigns are active.
  Expected and read-only, but budget for it as a per-restart cost, not a
  one-time seeding cost.

## Lint/format

```bash
make lint      # ruff check
make format    # ruff auto-fix + format
```

## MCP servers (Claude Code development)

The repo ships a project-level `.mcp.json` declaring the `chrome-devtools` MCP server, which the workstream verification step (`verifying-with-demo-scenarios` → `demo-scenario-verifier`) uses to drive the local `adk web` UI. It runs via `npx chrome-devtools-mcp@latest` — no install beyond Node.js. Claude Code prompts once per machine to approve project MCP servers (or set `"enableAllProjectMcpServers": true` in your `.claude/settings.local.json`).

## Corrections to README.md

`README.md` is client-facing and deliberately kept untouched, so factual drift is recorded here instead:

- README (line ~66) says the agent "delivers the code for live connectivity to the Veo3 engine and BlueZoo's BigQuery database recording real time audience analytics." Veo3 connectivity is real, but there is **no BigQuery (or any live BlueZoo) connectivity in the current code** — impressions come from mock data in a local **SQLite** database (`campaigns.db`, see `app/database/`), on every environment. Live BlueZoo API integration is planned Version 2 work (see `.docs/version2-plan/`, the BlueZoo live-data phase).

## Deploy

See `DEPLOYMENT.md` for Cloud Run / Vertex AI Agent Engine deployment, including one-time GCP setup and known gotchas (Python version, `global` region for Gemini 3, GCS permissions).

## Version 2 workstream setup notes

This section accumulates setup steps introduced by `.docs/version2-plan/` phases as they land — e.g. `APP_MODE` (Phase 6), a BlueZoo `AccessKey` secret (Phase 11), a PoS credential (Phase 12). Check `.docs/version2-plan/STATUS.md` for current progress.

- **Phase 1 (workstream 01):** all three model config values now default to GA IDs and are env-overridable via `AGENT_MODEL` (default `gemini-3.6-flash` since workstream 14), `IMAGE_GENERATION_MODEL` (default `gemini-3-pro-image`), and `VIDEO_GEN_MODEL` (default `veo-3.1-generate-001`) — set them in `app/.env` only when testing a different (e.g. preview) model. `scripts/smoke_media_models.py` smoke-tests Stage 1 + Stage 2 generation against whatever is configured (`--skip-video` for the cheap image-only check). Note `make install` runs bare `python`; on machines with only versioned interpreters, create the venv manually (`python3.12 -m venv .venv && .venv/bin/pip install -r app/requirements.txt`).
- **Phase 6 (workstream 06):** `APP_MODE=demo|connected` exists as a typed config value (`app/config.py`), default `demo`; invalid values fail startup with a `ValueError`. Nothing consumes it yet — Phase 11a resolves it to a data-provider selection internally (it stays the only user-facing mode knob). Both explicit deploy paths forward it (`scripts/deploy.sh` via `--set-env-vars`, `scripts/deploy_ae_inline.py` via its `env_vars` dict); `scripts/deploy_ae.sh` picks it up from `app/.env` automatically.
- **Phase 8 (workstream 08):** Workstream 08 added the `always-on` campaign category to the campaigns table's CHECK constraint. SQLite can't ALTER a CHECK, so a `campaigns.db` created before this change must be regenerated: `make reset-db`, then restart `make dev` (demo data repopulates automatically).
- **Phase 14a/14b (workstream 14):** agent default model is now `gemini-3.6-flash` (GA, Vertex global — pulled forward from Phase 16 step 3). Image/video generation defaults unchanged (`gemini-3-pro-image`, `veo-3.1-generate-001`); the Nano Banana 2 Lite comparison and Omni Flash prototype findings live in `.docs/version2-plan/working-docs/14-model-upgrades/`.
- **Phase 14c (workstream 14c):** opt-in, experimental post-generation visual video editing via Gemini Omni Flash's Interactions API, gated by `ENABLE_OMNI_EDIT` (`app/config.py`, default `false` — set `true` in `app/.env` to register `edit_video_with_omni` on the Review Agent). `OMNI_EDIT_MODEL` (default `gemini-omni-flash-preview`) is env-overridable for testing other models. Requires `google-genai>=2.14.0` (bumped from `>=1.55.0`, both in `app/requirements.txt` and `scripts/deploy_ae_inline.py`'s inline requirements list — the Interactions typed API doesn't exist on older SDK versions, and this import is unconditional at agent-module load, so a stale floor can break agent import even with the flag off). Dialogue/audio translation via the same API is confirmed **not supported** (live-tested, code-switched/unsynced output) — out of scope, `translate_video_dialogue()` is a documented `NotImplementedError` placeholder only. See `.docs/version2-plan/14c-omni-video-editing.md`.
- **Phase 16 (workstream 16):** two agent-behavior fixes shipped alongside the live test tier (both owner-approved, both routing/instruction changes, not schema changes): (a) the Campaign and Coordinator agents now resolve an existing product via `list_products` before creating a new one — the campaign-creation flow no longer onboards duplicate products for a product that's already in the catalog; (b) Google-Maps-link/map queries route to the Analytics Agent's `get_campaign_map_data` — the Campaign Agent now only answers plain store-address lookups (`get_campaign_locations`), its description says so explicitly. See the "Live tier" section above for `make test-live` setup and the flakiness watchlist.

## Local-first mode (Phase 15)

The app is local-first: with `GCS_BUCKET` **unset**, every asset (product
images, videos, thumbnails) lives under the local assets root and tool
responses never contain `storage.googleapis.com` URLs. GCS is an explicit
opt-in for cloud deploys (`GCS_BUCKET=<bucket>`); the old hardcoded default
bucket is gone.

**Check your `app/.env`:** older dev `.env` files set `GCS_BUCKET` — as long
as that line is present you are in GCS mode. Comment it out (or delete it)
for local-first mode.

- `LOCAL_ASSETS_DIR` (optional): local asset root; defaults to the project
  root, giving the pre-existing `selected/` and `generated/` folders plus the
  new `product-images/`.
- `DEMO_DATASET=fashion|none` (default `fashion`): which demo catalog gets
  seeded at startup. `fashion` = today's full demo (22 fashion + 6 retail
  core products, 4 campaigns). `none` = empty catalog — the from-scratch
  onboarding path (`docs/demo-scenarios/from-scratch-onboarding.md`).
  This is a demo-scoped dataset selector, NOT a mode knob — `APP_MODE`
  remains the only mode env var.

### Demo asset bundle (product images without GCS)

Demo product images ship as an owner-hosted Google Drive zip. `make dev` runs
the installer automatically before starting the server (a no-op once
installed, a graceful skip when unconfigured), or run it directly:

```bash
make demo-assets                              # uses DEMO_ASSETS_DRIVE_ID
make demo-assets-from-file FILE=x.zip         # or a local bundle
# equivalently: python -m scripts.demo_assets install [--from-file x.zip]
```

Unset `DEMO_ASSETS_DRIVE_ID` → the installer skips gracefully; the app still
works, seeded products just report `image_status: missing` locally.

**Owner: publishing/refreshing the bundle** — collect the demo images into a
folder tree (`<src>/product-images/<file>...`), then:

```bash
make demo-assets-build SRC=<src> OUT=demo-assets.zip
# (wraps: python -m scripts.demo_assets build --source <src> --out demo-assets.zip)
# upload demo-assets.zip to Google Drive (anyone-with-link), then set
# DEMO_ASSETS_DRIVE_ID=<drive-file-id> in app/.env
```

### Onboarding products from the CLI

Same functions as the Campaign agent's tools:

```bash
python -m scripts.onboard_products create --name "Aurora Cold Brew 330ml" --category beverage --attr volume_ml=330
python -m scripts.onboard_products import-folder /path/to/images --category homeware
python -m scripts.onboard_products generate-image --product-id 3
```
