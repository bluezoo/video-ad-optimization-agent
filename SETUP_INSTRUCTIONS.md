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
