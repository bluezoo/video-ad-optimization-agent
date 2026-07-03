# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Google ADK multi-agent system that closes the loop on in-store video ad optimization: Veo3 generates candidate video ads, BlueZoo sensors measure impressions, revenue-per-impression (RPI) picks winners, and winners seed the next generation round. Root agent is a Coordinator that routes to a Campaign Agent, Media Agent, and Analytics Agent, plus Review tools for human-in-the-loop (HITL) video activation.

Key source layout: `app/agent.py` (agent graph), `app/config.py` (models/env), `app/tools/` (campaign, video, review, metrics, maps, image tools), `app/database/` (SQLite + mock data), `app/models/` (Pydantic models), `app/agent_engine_app.py` (Agent Engine entrypoint).

## Commands

```bash
make install        # create .venv, install app/requirements.txt
make dev            # run ADK web UI locally on :8501 (alias: make playground)
make test           # unit + integration (default; skips slow tests)
make test-unit      # tests/unit only, ~4s, no LLM calls — fastest feedback loop
make test-e2e       # tests/e2e workflow tests, ~1s, no LLM calls
make test-integration  # tests/integration, uses real LLM via AgentEvaluator eval_sets
make test-all       # everything including slow Veo tests, ~10+ min
make test-coverage  # pytest --cov=app, HTML report in htmlcov/
make reset-db       # wipe campaigns.db, next `make dev` repopulates demo data
```

Run a single test: `pytest tests/unit/test_campaign_tools.py::TestClass::test_name -v`.

Pytest markers: `slow` (>30s, Veo/chart generation), `integration` (needs LLM), `veo` (needs Veo 3.1 API), `e2e`.

Lint/format with ruff (config in `ruff.toml`): `make lint` (check only), `make format` (auto-fix + format). A `PostToolUse` hook (`.claude/settings.json`) also runs `make test-unit` automatically after edits to `app/**/*.py`.

## Repo etiquette

- Do not add a `Co-Authored-By: Claude` (or similar AI attribution) trailer to commit messages.

## Environment

Vertex AI path: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`, `GCS_BUCKET`. AI Studio path: `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, `GOOGLE_API_KEY`, `GCS_BUCKET`. Optional: `GOOGLE_MAPS_API_KEY` (or `MAPS_API_KEY`) for maps tools — tests skip cleanly if unset. Vars go in `app/.env`.

## Gotchas

- **Gemini 3 requires `GOOGLE_CLOUD_LOCATION=global`.** `MODEL`, `IMAGE_GENERATION`, and `VEO_MODEL` in `app/config.py` are all Gemini 3 / Veo 3.1 preview models — don't point deploys at a regional endpoint for them.
- **Agent Engine only supports Python 3.9–3.13**, not 3.14+. `make deploy-ae-global` auto-selects `.venv-deploy` (Python 3.12) or falls back to `python3.12`/`python3.11` — see the `DEPLOY_PYTHON` logic in the Makefile.
- **`BuiltInCodeExecutor` cannot be combined with function-calling tools** in ADK — they're mutually exclusive on the same agent (see comment in `app/agent.py`).
- Deploying to Agent Engine requires granting `roles/storage.objectAdmin` on the GCS bucket to the Reasoning Engine service agent (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`) — run `make setup-ae-permissions` or it's handled automatically by `scripts/deploy_ae_inline.py`.
- DB path differs by environment (see `app/config.py`): project root locally, `app/campaigns.db` on Cloud Run, `/tmp/campaigns.db` on Agent Engine (ephemeral, repopulates from mock data on restart).
- Tests run against a **copy** of `campaigns.db`, never the real one — see `tests/conftest.py` fixtures (`test_db`, `shared_test_db`, `fresh_test_db`).
