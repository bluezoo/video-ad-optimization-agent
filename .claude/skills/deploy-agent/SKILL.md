---
name: deploy-agent
description: Deploy the video-ad-optimization-agent to Google Cloud Run or Vertex AI Agent Engine, including one-time GCP setup and permission fixes. Use when the user asks to deploy, redeploy, or set up GCP for this project.
disable-model-invocation: true
---

Guide the user through deploying this ADK agent. Confirm the target before running anything destructive or billable.

## 1. Pick a target

Ask which deployment the user wants if not already clear:

- **Cloud Run** — dev/demo use, gives a web UI at `/dev-ui`. Command: `make deploy` (add `--trace` via `make deploy-trace`).
- **Agent Engine, global region (recommended for Gemini 3)** — production, managed sessions, no web UI. Command: `make deploy-ae-global` (add `-trace` / `-dry-run` variants).
- **Agent Engine, us-central1 (legacy CLI)** — `make deploy-ae`. Only use if the global-region path is unavailable; it will not correctly serve Gemini 3 models without the `GlobalAdkApp` workaround already in `app/agent_engine_app.py`.

## 2. One-time GCP setup (skip if already done)

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com storage.googleapis.com aiplatform.googleapis.com maps-backend.googleapis.com
./scripts/setup_gcp.sh   # creates GCS bucket, uploads product images
```

Verify: `gcloud storage ls gs://YOUR_BUCKET_NAME/product-images/` should list ~22 images.

## 3. Set required env vars

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GCS_BUCKET="your-bucket-name"
export GOOGLE_MAPS_API_KEY="your-maps-key"   # optional, maps tools degrade gracefully without it
```

## 4. Deploy

Run the `make` target for the chosen path (step 1). For Agent Engine deployments, always prefer `-dry-run` first if the user hasn't deployed before, to preview the command.

**Python version gotcha**: Agent Engine requires Python 3.9–3.13, not 3.14+. `make deploy-ae-global` auto-selects `.venv-deploy` (Python 3.12) or falls back to `python3.12`/`python3.11` — if deployment fails with a Python version error, check `python3 --version` and create `.venv-deploy` with a compatible interpreter.

**Region gotcha**: All Gemini 3 models (`gemini-3-flash-preview`, `gemini-3-pro-image-preview`, `veo-3.1-generate-preview`) require `global` region. If you see `Publisher Model ... was not found (404)`, the deployment is pointed at a regional endpoint instead of `global`.

## 5. Grant GCS permissions (Agent Engine only)

Agent Engine writes generated videos/thumbnails to GCS via a dedicated service account that needs `storage.objectAdmin`. `scripts/deploy_ae_inline.py` grants this automatically, but if you see `403 Forbidden` on GCS uploads, run:

```bash
make setup-ae-permissions
```

## 6. Verify the deployment

- Cloud Run: `gcloud run services describe ad-campaign-agent --region=us-central1 --format='value(status.url)'`, then open `<url>/dev-ui`.
- Agent Engine: `gcloud ai reasoning-engines list --region=us-central1` (or `--region=global`), then query with the Python SDK or REST snippet in `DEPLOYMENT.md`.

Tail logs if something looks wrong: `gcloud run services logs tail ad-campaign-agent --region=us-central1` (Cloud Run only).

Refer to `DEPLOYMENT.md` for the full troubleshooting table (model-not-found, permission errors, PIL missing, maps key missing, video-generation timeouts).
