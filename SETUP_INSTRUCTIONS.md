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
```

## Run locally

```bash
make dev            # ADK web UI on :8501 (alias: make playground)
```

Open the printed local URL. `make reset-db` wipes `campaigns.db` and repopulates demo data on the next `make dev`.

## Metrics glossary

`docs/METRICS.md` is the single source of truth for what every metric means (impressions, RPI, revenue, circulation, dwell time), aligned to BlueZoo's own vocabulary — read it before touching any metric-related code. It supersedes the metric explanations scattered through code comments and the README's marketing prose; where they disagree, `docs/METRICS.md` wins. (README.md itself stays untouched per this file's header note.)

## Test

```bash
make test-unit         # tests/unit, ~4s, no LLM calls — fastest feedback loop
make test-e2e           # tests/e2e workflow tests, ~1s, no LLM calls
make test-integration   # tests/integration, uses a real LLM via AgentEvaluator eval_sets
make test               # unit + integration (default; skips slow tests)
make test-all            # everything, including slow Veo tests, ~10+ min
make test-coverage       # pytest --cov=app, HTML report in htmlcov/
```

Run a single test: `pytest tests/unit/test_campaign_tools.py::TestClass::test_name -v`.

**Test isolation note:** Prior to the database late-binding fix (workstream version_2_bug-fixes-and-cleanup), unit tests leaked writes into the real `campaigns.db` because `DB_PATH` was bound at import time, preventing test fixtures from patching it. Older checkouts with accumulated junk campaigns should run `make reset-db` once to clear them. The fix ensures all tests use isolated temporary database copies.

**`make test-integration` requires the ADK eval extra:** `pip install "google-adk[eval]"` (into `.venv`). Without it, `AgentEvaluator.evaluate` raises a *lazy* ImportError that the test suite's broad `except ImportError` silently converts into "google.adk.evaluation not available" skips — the suite reports green-looking "5 skipped" while running nothing. (Found during workstream 01; the over-broad catch itself is Phase 2, item 7.) The suite also needs `app/.env` sourced or present (real LLM calls).

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

- **Phase 1 (workstream 01):** all three model config values now default to GA IDs and are env-overridable via `AGENT_MODEL` (default `gemini-3.5-flash`), `IMAGE_GENERATION_MODEL` (default `gemini-3-pro-image`), and `VIDEO_GEN_MODEL` (default `veo-3.1-generate-001`) — set them in `app/.env` only when testing a different (e.g. preview) model. `scripts/smoke_media_models.py` smoke-tests Stage 1 + Stage 2 generation against whatever is configured (`--skip-video` for the cheap image-only check). Note `make install` runs bare `python`; on machines with only versioned interpreters, create the venv manually (`python3.12 -m venv .venv && .venv/bin/pip install -r app/requirements.txt`).
- **Phase 6 (workstream 06):** `APP_MODE=demo|connected` exists as a typed config value (`app/config.py`), default `demo`; invalid values fail startup with a `ValueError`. Nothing consumes it yet — Phase 11a resolves it to a data-provider selection internally (it stays the only user-facing mode knob). Both explicit deploy paths forward it (`scripts/deploy.sh` via `--set-env-vars`, `scripts/deploy_ae_inline.py` via its `env_vars` dict); `scripts/deploy_ae.sh` picks it up from `app/.env` automatically.
- **Phase 8 (workstream 08):** Workstream 08 added the `always-on` campaign category to the campaigns table's CHECK constraint. SQLite can't ALTER a CHECK, so a `campaigns.db` created before this change must be regenerated: `make reset-db`, then restart `make dev` (demo data repopulates automatically).

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
