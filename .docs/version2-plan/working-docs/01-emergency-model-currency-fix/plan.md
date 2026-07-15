# Phase 0: Emergency Model Currency Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Exception (approved):** this phase is rated Trivial in `00-overview.md`, so per CLAUDE.md's trivial-phase fast path these tasks execute inline in the main session — no per-task subagent dispatch. Everything else (checkpoints, verification, PR) stays standard.

**Goal:** Swap the two deprecated preview media-model IDs in `app/config.py` for their GA replacements, made env-overridable so preview models can be swapped in for testing (approved addendum), with stale references fixed and a real Stage 1 + Stage 2 generation proving the new IDs work. Per plan-approval feedback, the video constant is renamed `VEO_MODEL` → `VIDEO_GEN_MODEL` (model-agnostic — Omni or Veo can back it; aligns with the image-side naming).

**Architecture:** Config-level change plus one mechanical rename — every call site already reads `IMAGE_GENERATION`/`VEO_MODEL` from `app/config.py` (verified: `video_tools.py:237,299,581,960`, `maps_tools.py:1279`, `metrics_tools.py:981`; `VEO_MODEL` is consumed only by `video_tools.py`). The two constants become `os.environ.get(...)` lookups with GA defaults. A new committed smoke script provides the before/after release gate and doubles as the preview-model test harness the owner asked for.

**Tech Stack:** Python, google-genai SDK (Vertex path), pytest, existing `make` targets.

## Global Constraints

- GA defaults exactly: `IMAGE_GENERATION` → `"gemini-3-pro-image"`, `VIDEO_GEN_MODEL` → `"veo-3.1-generate-001"` (re-verified current on Vertex, 2026-07-14).
- Env override names exactly: `IMAGE_GENERATION_MODEL` and `VIDEO_GEN_MODEL` (approved addendum + plan-approval rename).
- Constant rename `VEO_MODEL` → `VIDEO_GEN_MODEL` everywhere: `app/config.py:28`, `app/tools/video_tools.py:51,297,299,581,958,960`, plus the `CLAUDE.md:70` gotcha line and the phase doc's validation grep (both reference `VEO_MODEL` by name).
- `MODEL = "gemini-3-flash-preview"` (config.py:24) is untouched — confirmed no near-term shutdown.
- `README.md` untouched. `video_tools.py:18` docstring and `agent.py:200` "Gemini 2.0" texts untouched (Phase 1, item 6).
- `app/.env` is gitignored (`.gitignore:23`) and must never be committed.
- No `Co-Authored-By` trailers in commits.
- Vertex env for smoke tests: project `kaggle-on-gcp`, location `global`, bucket `kaggle-on-gcp-ad-campaign-assets` (approved).

---

### Task 1: Env bootstrap + committed smoke script + baseline run

**Files:**
- Create: `app/.env` (NOT committed — gitignored)
- Create: `scripts/smoke_media_models.py` (committed)
- Modify: `.docs/version2-plan/working-docs/01-emergency-model-currency-fix/WORK_LOG.md` (append baseline result)

**Interfaces:**
- Produces: `scripts/smoke_media_models.py` runnable as `.venv/bin/python scripts/smoke_media_models.py [--skip-video]`, exit 0 on success, non-zero on failure. Task 4 re-runs it unchanged.

- [ ] **Step 1: Create `app/.env`** (worktree has none; values approved by owner)

```bash
cat > app/.env << 'EOF'
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=kaggle-on-gcp
GOOGLE_CLOUD_LOCATION=global
GCS_BUCKET=kaggle-on-gcp-ad-campaign-assets
EOF
git check-ignore app/.env && echo "ignored OK"
```

Expected: prints `app/.env` then `ignored OK`. If `git check-ignore` fails, STOP — do not proceed with an .env that could be committed.

- [ ] **Step 2: Install the worktree venv**

Run: `make install`
Expected: `.venv` created, `app/requirements.txt` installed, exit 0.

- [ ] **Step 3: Write the smoke script**

Create `scripts/smoke_media_models.py`:

```python
"""Smoke test for the two media-generation models (Stage 1 image, Stage 2 video).

Run from the repo root with app/.env populated:

    set -a; source app/.env; set +a
    .venv/bin/python scripts/smoke_media_models.py            # Stage 1 + Stage 2
    .venv/bin/python scripts/smoke_media_models.py --skip-video  # Stage 1 only

Exits 0 on success. Also usable to try preview models without code changes:

    IMAGE_GENERATION_MODEL=<some-preview-id> .venv/bin/python scripts/smoke_media_models.py --skip-video
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.models.variation import CreativeVariation  # noqa: E402
from app.tools.video_tools import animate_scene_with_veo, generate_scene_image  # noqa: E402

# Tolerates both constant names so the Task-1 baseline (pre-rename config)
# and every later run (post-rename) use the same script unchanged.
IMAGE_MODEL = config.IMAGE_GENERATION
VIDEO_MODEL = getattr(config, "VIDEO_GEN_MODEL", None) or getattr(config, "VEO_MODEL")

# Minimal product dict; prompt builders use .get() with defaults for every key.
PRODUCT = {
    "name": "sage-satin-camisole",
    "details": "A sage green satin camisole with delicate lace trim",
    "category": "summer",
    "color": "sage green",
    "fabric": "satin",
}


async def main() -> int:
    variation = CreativeVariation(name="smoke-test-studio")

    print(f"Stage 1 model: {IMAGE_MODEL}")
    scene_bytes, _ = await generate_scene_image(PRODUCT, variation)
    print(f"Stage 1 OK: {len(scene_bytes)} bytes")

    if "--skip-video" in sys.argv:
        print("Stage 2 skipped (--skip-video)")
        return 0

    print(f"Stage 2 model: {VIDEO_MODEL}")
    video_bytes, _ = await animate_scene_with_veo(
        scene_bytes, PRODUCT, variation, duration_seconds=4
    )
    print(f"Stage 2 OK: {len(video_bytes)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 4: Baseline run against the CURRENT (preview) IDs — record, don't fix**

```bash
set -a; source app/.env; set +a
.venv/bin/python scripts/smoke_media_models.py 2>&1 | tail -20
```

Expected: **either** outcome is a valid baseline — success (Vertex still tolerating the preview IDs) or a model-not-found/permission error (deprecation already biting). Veo Stage 2 takes ~1-4 min (polls every 20 s). Record the exact outcome verbatim in the next step. If the failure is *not* model-related (auth, bucket, quota), STOP and fix the environment first — the baseline must isolate model currency.

- [ ] **Step 5: Append baseline result to WORK_LOG.md**

Append (with real timestamp and observed output):

```markdown
## <date time> — Task 1: baseline smoke vs preview IDs
Stage 1 (gemini-3-pro-image-preview): <succeeded / failed: exact error>
Stage 2 (veo-3.1-generate-preview): <succeeded / failed: exact error>
```

- [ ] **Step 6: Lint and commit** (script + log only — never `app/.env`)

```bash
make lint
git add scripts/smoke_media_models.py .docs/version2-plan/working-docs/01-emergency-model-currency-fix/WORK_LOG.md
git status --short   # confirm app/.env NOT listed
git commit -m "Add media-model smoke script; record preview-ID baseline"
```

---

### Task 2: Env-overridable GA model config + `VIDEO_GEN_MODEL` rename (TDD)

**Files:**
- Create: `tests/unit/test_config.py`
- Modify: `app/config.py:26-28`
- Modify: `app/tools/video_tools.py:51,297,299,581,958,960` (rename only)

**Interfaces:**
- Produces: `app.config.IMAGE_GENERATION` (default `"gemini-3-pro-image"`, env override `IMAGE_GENERATION_MODEL`) and `app.config.VIDEO_GEN_MODEL` (default `"veo-3.1-generate-001"`, env override `VIDEO_GEN_MODEL`) — the old `VEO_MODEL` name no longer exists. `video_tools.py` is its only consumer and is renamed in the same commit.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config.py`:

```python
"""Unit tests for media-model configuration (Phase 0: model currency fix)."""

import importlib

import pytest

import app.config as config_module


@pytest.fixture(autouse=True)
def _reload_config_after_test(monkeypatch):
    """Each test reloads app.config; restore a clean-env reload afterwards."""
    yield
    monkeypatch.delenv("IMAGE_GENERATION_MODEL", raising=False)
    monkeypatch.delenv("VIDEO_GEN_MODEL", raising=False)
    importlib.reload(config_module)


def test_media_model_defaults_are_ga_ids(monkeypatch):
    monkeypatch.delenv("IMAGE_GENERATION_MODEL", raising=False)
    monkeypatch.delenv("VIDEO_GEN_MODEL", raising=False)
    cfg = importlib.reload(config_module)
    assert cfg.IMAGE_GENERATION == "gemini-3-pro-image"
    assert cfg.VIDEO_GEN_MODEL == "veo-3.1-generate-001"


def test_media_models_are_env_overridable(monkeypatch):
    monkeypatch.setenv("IMAGE_GENERATION_MODEL", "fake-image-preview-id")
    monkeypatch.setenv("VIDEO_GEN_MODEL", "fake-video-preview-id")
    cfg = importlib.reload(config_module)
    assert cfg.IMAGE_GENERATION == "fake-image-preview-id"
    assert cfg.VIDEO_GEN_MODEL == "fake-video-preview-id"


def test_old_veo_model_name_is_gone():
    cfg = importlib.reload(config_module)
    assert not hasattr(cfg, "VEO_MODEL")
```

(Note: reloading `app.config` doesn't rebind names other modules imported with `from ..config import X` — irrelevant here, these tests assert on the module's own attributes.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_config.py -v`
Expected: all 3 FAIL — `test_media_model_defaults_are_ga_ids` and `test_media_models_are_env_overridable` with `AttributeError: ... has no attribute 'VIDEO_GEN_MODEL'`; `test_old_veo_model_name_is_gone` because `VEO_MODEL` still exists.

- [ ] **Step 3: Implement the config change**

In `app/config.py`, replace lines 26-28:

```python
# Media generation models
IMAGE_GENERATION = "gemini-3-pro-image-preview"  # For scene image generation (Stage 1)
VEO_MODEL = "veo-3.1-generate-preview"  # For video animation (Stage 2)
```

with:

```python
# Media generation models — GA IDs as defaults, env-overridable so preview
# models (e.g. Nano Banana 2 Lite, Gemini Omni Flash) can be swapped in for
# pipeline testing without code changes (evaluation itself is Phase 13a/13b).
# VIDEO_GEN_MODEL is deliberately model-agnostic (Veo today, possibly Omni later).
IMAGE_GENERATION = os.environ.get("IMAGE_GENERATION_MODEL", "gemini-3-pro-image")  # Stage 1 scene images
VIDEO_GEN_MODEL = os.environ.get("VIDEO_GEN_MODEL", "veo-3.1-generate-001")  # Stage 2 video animation
```

Then rename the consumer (`app/tools/video_tools.py` is the only importer): change `VEO_MODEL,` to `VIDEO_GEN_MODEL,` in the import at line 51, and replace the five usages at lines 297, 299, 581, 958, 960 (`{VEO_MODEL}` in the two debug prints, `model=VEO_MODEL` in the three API calls) with `VIDEO_GEN_MODEL`. Verify completeness:

```bash
grep -rn "VEO_MODEL" app/ tests/ scripts/
```

Expected: exactly one hit — the `getattr(config, "VEO_MODEL")` fallback string in `scripts/smoke_media_models.py` (kept deliberately so the script runs against both pre- and post-rename checkouts). Nothing in `app/` or `tests/`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_config.py -v`
Expected: 2 PASSED. (The `PostToolUse` hook also auto-runs `make test-unit` after the edit — expect it green.)

- [ ] **Step 5: Run the full unit suite**

Run: `make test-unit`
Expected: all pass (tests reference no model IDs — verified during kickoff research).

- [ ] **Step 6: Commit**

```bash
git add app/config.py tests/unit/test_config.py
git commit -m "Swap deprecated preview media models for GA IDs, env-overridable"
```

---

### Task 3: Fix stale references (code comments, doc tables, CLAUDE.md gotcha, phase-doc amendments)

**Files:**
- Modify: `app/tools/video_tools.py:218` and `:966` (comments only)
- Modify: `DEMO_GUIDE.md:435-440` (model table)
- Modify: `DEPLOYMENT.md:462-467` (model table)
- Modify: `CLAUDE.md:70` (gotcha line references `VEO_MODEL` and calls the media models preview)
- Modify: `.docs/version2-plan/01-emergency-model-currency-fix.md` (open-question amendment + rename provenance note on the validation grep)

**Interfaces:** none — comments and docs only; no behavior change.

- [ ] **Step 1: Fix `video_tools.py:218`** — replace:

```python
    # Use Gemini 2.0 Flash Exp for image generation (imagen-3.0-generate-002 alternative)
    # For now, using native image generation via Gemini
```

with:

```python
    # Native image generation via the configured Gemini image model
    # (config.IMAGE_GENERATION — GA default gemini-3-pro-image, env-overridable)
```

- [ ] **Step 2: Fix `video_tools.py:966`** — replace:

```python
                # Note: enhance_prompt is NOT supported by veo-3.1-generate-preview
```

with:

```python
                # Note: enhance_prompt is NOT supported by the Veo 3.1 models
```

- [ ] **Step 3: Update `DEMO_GUIDE.md` model table** (lines 435-440; the whole table is stale — it predates even the current preview IDs). Replace:

```markdown
| Purpose | Model |
|---------|-------|
| All Agents | `gemini-2.5-pro` |
| Scene Images | `gemini-2.5-flash-image` |
| Video Animation | `veo-3.1-generate-preview` |
| Charts/Maps | `gemini-2.5-flash-image` |
```

with:

```markdown
| Purpose | Model |
|---------|-------|
| All Agents | `gemini-3-flash-preview` |
| Scene Images | `gemini-3-pro-image` |
| Video Animation | `veo-3.1-generate-001` |
| Charts/Maps | `gemini-3-pro-image` |
```

No other DEMO_GUIDE.md changes (it stays fashion-specific per CLAUDE.md; owner approved this table row correction only).

- [ ] **Step 4: Update `DEPLOYMENT.md` model table** (lines 464-467). Replace:

```markdown
| Agent Reasoning | `gemini-3-flash-preview` | `global` |
| Scene Image Generation | `gemini-3-pro-image-preview` | `global` |
| Video Animation | `veo-3.1-generate-preview` | `global` |
| Charts & Maps | `gemini-3-pro-image-preview` | `global` |
```

with:

```markdown
| Agent Reasoning | `gemini-3-flash-preview` | `global` |
| Scene Image Generation | `gemini-3-pro-image` (default; `IMAGE_GENERATION_MODEL` env override) | `global` |
| Video Animation | `veo-3.1-generate-001` (default; `VIDEO_GEN_MODEL` env override) | `global` |
| Charts & Maps | `gemini-3-pro-image` (default; `IMAGE_GENERATION_MODEL` env override) | `global` |
```

- [ ] **Step 4b: Update the `CLAUDE.md:70` gotcha line** (durable-knowledge promotion — it names `VEO_MODEL` and calls all three models preview, both stale after this phase). Replace:

```markdown
- **Gemini 3 preview models need `GOOGLE_CLOUD_LOCATION=global`** (the `us`/`eu` multi-region endpoints also work; single regions like `us-central1` don't). `MODEL`, `IMAGE_GENERATION`, and `VEO_MODEL` in `app/config.py` are all Gemini 3 / Veo 3.1 preview models — don't point deploys at a single-region endpoint for them.
```

with:

```markdown
- **Gemini 3 models need `GOOGLE_CLOUD_LOCATION=global`** (the `us`/`eu` multi-region endpoints also work; single regions like `us-central1` don't). `MODEL` (preview), `IMAGE_GENERATION`, and `VIDEO_GEN_MODEL` in `app/config.py` are all Gemini 3 / Veo 3.1 models — don't point deploys at a single-region endpoint for them. The two media models default to GA IDs and are env-overridable (`IMAGE_GENERATION_MODEL`, `VIDEO_GEN_MODEL`) for testing preview models.
```

- [ ] **Step 5: Amend the phase doc's open question 1** (research finding, provenance-marked per the Discoveries convention). In `.docs/version2-plan/01-emergency-model-currency-fix.md`, append directly under the first open-question bullet (the one about `MODEL = "gemini-3-flash-preview"`):

```markdown
  > **Amended (workstream 01, 2026-07-14):** Answered during kickoff research — Google's deprecations page lists `gemini-3-flash-preview` as deprecated 2025-12-17 with **"no shutdown date announced"** (successor: `gemini-3.5-flash`). No near-term cutoff, so it stays out of Phase 0's scope; revisit if a shutdown date is announced.
```

Also run `grep -n "gemini-3-flash-preview" .docs/version2-plan/99-open-questions.md` — if the consolidated list carries this question too, add the same amendment there; if not, no change.

Additionally, add a rename provenance note to the phase doc's Validation section (its grep `VEO_MODEL\s*=` can no longer match). Directly under the first validation checkbox in `.docs/version2-plan/01-emergency-model-currency-fix.md`, append:

```markdown
  > **Amended (workstream 01, 2026-07-14):** at plan approval the owner renamed the constant/env var `VEO_MODEL` → `VIDEO_GEN_MODEL` (model-agnostic — Veo today, possibly Omni later; matches the image-side naming). The grep is therefore `grep -n 'IMAGE_GENERATION\s*=\|VIDEO_GEN_MODEL\s*=' app/config.py`.
```

- [ ] **Step 6: Run the phase doc's validation greps**

```bash
grep -rn "gemini-3-pro-image-preview\|veo-3.1-generate-preview" --include="*.py" --include="*.md" --include="*.sh" . | grep -v ".docs/" | grep -v ".claude/"
grep -n 'IMAGE_GENERATION\s*=\|VIDEO_GEN_MODEL\s*=' app/config.py
grep -rn "Gemini 2.0 Flash Exp" app/
```

Expected: grep 1 → no output. Grep 2 → the two `os.environ.get` lines with GA defaults. Grep 3 → exactly two hits, `app/tools/video_tools.py:18` and `app/agent.py:200` (Phase 1's, untouched).

- [ ] **Step 7: Commit**

```bash
git add app/tools/video_tools.py DEMO_GUIDE.md DEPLOYMENT.md CLAUDE.md .docs/version2-plan/01-emergency-model-currency-fix.md .docs/version2-plan/99-open-questions.md
git commit -m "Fix stale model references in comments, doc tables, and CLAUDE.md; amend phase doc"
```

(Drop `99-open-questions.md` from the `git add` if Step 5 found no hit there.)

---

### Task 4: Post-swap smoke run + full suite (release gate)

**Files:**
- Modify: `.docs/version2-plan/working-docs/01-emergency-model-currency-fix/WORK_LOG.md` (append results)

**Interfaces:**
- Consumes: `scripts/smoke_media_models.py` from Task 1, new config from Task 2.

- [ ] **Step 1: Run the smoke script against the GA IDs**

```bash
set -a; source app/.env; set +a
.venv/bin/python scripts/smoke_media_models.py 2>&1 | tail -20
```

Expected: `Stage 1 model: gemini-3-pro-image` … `Stage 1 OK: <n> bytes` … `Stage 2 model: veo-3.1-generate-001` … `Stage 2 OK: <n> bytes`, exit 0. **Both stages must succeed — this is the phase's release gate.** If either fails, stop and debug via systematic-debugging before touching anything else.

- [ ] **Step 2: Prove the env override works end-to-end (Stage 1 only, cheap)**

```bash
IMAGE_GENERATION_MODEL=gemini-3-pro-image .venv/bin/python scripts/smoke_media_models.py --skip-video
```

Expected: `Stage 1 model: gemini-3-pro-image` printed via the override path, Stage 1 OK. (Uses the GA ID as the override value — proves the mechanism without depending on any preview model's availability.)

- [ ] **Step 3: Full test suites**

```bash
make test-unit && make test-e2e && make test-integration
```

Expected: all pass. (`test-integration` calls the live orchestration model via AgentEvaluator — unaffected by this change but required by the phase doc.)

- [ ] **Step 4: Append results to WORK_LOG.md and commit**

```markdown
## <date time> — Task 4: post-swap release gate
Stage 1 (gemini-3-pro-image): OK, <n> bytes. Stage 2 (veo-3.1-generate-001): OK, <n> bytes.
Env-override path verified (IMAGE_GENERATION_MODEL). test-unit / test-e2e / test-integration: all pass.
```

```bash
git add .docs/version2-plan/working-docs/01-emergency-model-currency-fix/WORK_LOG.md
git commit -m "Record Phase 0 release-gate results"
```

---

### Task 5: Seed `docs/demo-scenarios/fashion.md` (first demo scenario)

**Files:**
- Create: `docs/demo-scenarios/fashion.md`

**Interfaces:**
- Produces: the scenario file `verifying-with-demo-scenarios` dispatches to the `demo-scenario-verifier` subagent (adk web on :8501). Later workstreams extend this file with more fashion scenarios.

- [ ] **Step 1: Create the scenario file**

Create `docs/demo-scenarios/fashion.md`:

```markdown
# Demo Scenarios — Fashion (current default vertical)

Scenario files under `docs/demo-scenarios/` are executable scripts for the
`demo-scenario-verifier` subagent (see `.claude/agents/`), driven through a
local `make dev` instance (adk web, port 8501) via chrome-devtools MCP.
Modeled on `DEMO_GUIDE.md` (which stays the fashion-specific, client-facing
walkthrough — this file is the automation-facing distillation).

Prereqs for all scenarios: `app/.env` configured (Vertex path, location
`global`), `make dev` running on :8501, demo DB populated (delete
`campaigns.db` and restart `make dev` to repopulate).

## Scenario F1: End-to-end video generation (Stage 1 + Stage 2)

**Purpose:** Proves the media pipeline works against the configured
image/video models — the release gate for any model-config change.

**Steps:**
1. Open `http://localhost:8501`, select the `app` agent.
2. Send: `Show me all campaigns`.
   - **Expect:** a campaign list including `sage-satin-camisole - The Grove`
     (4 demo campaigns total), no tool errors.
3. Send: `Generate 1 new video variation for the sage-satin-camisole campaign.
   Use a studio setting with an elegant mood.`
   - **Expect:** the Media Agent runs the two-stage pipeline — trace shows a
     Stage 1 scene-image generation followed by a Stage 2 Veo animation
     (polling messages are normal; Stage 2 takes ~1-4 minutes).
4. Wait for completion.
   - **Expect:** a success response referencing a generated video (filename
     matching `sage-satin-camisole-<MMDDYY>-<variation>.mp4`), with the video
     stored and registered for review (pending_review status), and no
     exception text anywhere in the response or trace.

**Pass:** all expectations met. **Fail:** any stage errors, times out
(>10 min), or the response contains a model-not-found / permission error.
```

- [ ] **Step 2: Commit**

```bash
git add docs/demo-scenarios/fashion.md
git commit -m "Seed fashion demo scenario file for verification runs"
```

---

## After the plan (lifecycle, not tasks)

1. `verifying-with-demo-scenarios` — run Scenario F1 via the `demo-scenario-verifier` subagent; append checkpoint 5 to WORK_LOG.md.
2. `requesting-code-review` on the whole branch.
3. `finishing-a-development-branch` — PR into `version_2`, self-merge, update STATUS.md.
