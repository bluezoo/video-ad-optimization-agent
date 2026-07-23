# Phase 16 kickoff research — repo claim verification

Date: 2026-07-23 (session date). Worktree: `.claude/worktrees/version_2_live-api-testing`
(branch `version_2_live-api-testing` off `version_2`; verification done read-only except this file).
All paths below are relative to the worktree root unless absolute.

Verdict shorthand: **CONFIRMED** = phase-doc claim matches current code; **STALE** = claim no
longer true; **PARTIAL** = true with caveats.

---

## 1. tests/integration/ layout — CONFIRMED

Files (complete):

- `tests/integration/__init__.py`
- `tests/integration/test_agents.py`
- `tests/integration/eval_sets/.gitkeep`
- `tests/integration/eval_sets/analytics_agent.test.json`
- `tests/integration/eval_sets/campaign_agent.test.json`
- `tests/integration/eval_sets/coordinator.test.json`
- `tests/integration/eval_sets/media_agent.test.json`
- `tests/integration/eval_sets/review_agent.test.json`

**No `tests/integration/conftest.py` exists** (step 1 must create it). **No `test_config.json`
anywhere in the repo** (`find` over the whole tree, excluding .venv, returned nothing) — step 2
must create the criteria file.

Representative eval set (`tests/integration/eval_sets/campaign_agent.test.json`): 4 eval cases,
all pin **direct tool calls** with no `transfer_to_agent` wrapping, and 3 of 4 have an **empty
reference response**. E.g. case `list-all-campaigns` (lines 6–28):

- `user_content`: "What campaigns do we have?"
- `final_response`: `{"parts": [{"text": ""}], "role": "model"}` (empty string reference)
- `intermediate_data.tool_uses`: `[{"name": "list_campaigns", "args": {}}]` — direct, no transfer.

The one non-empty reference (`create-campaign-beverage`, lines 76–97) pins a full sentence
("Your campaign for Aurora Cold Brew at Target Downtown in Austin, Texas has been created.") and
a direct `create_campaign` call with `product_id: 23` hard-coded. This matches the phase doc's
step 2 claim (direct tool calls + reference responses that real runs won't match) exactly.

`tests/integration/test_agents.py`: 5 per-agent tests + 1 `slow` multi-run test, all
`AgentEvaluator.evaluate(agent_module="app.agent", ...)` with `num_runs=1`. `_INFRA_MARKERS`
tuple at `tests/integration/test_agents.py:61-65` (credential/403/quota/429/503/etc.);
`_xfail_if_infrastructure` at lines 68–73 xfails only on those, re-raises otherwise. Note the
phase doc's "narrowed `_INFRA_MARKERS`" language refers to this existing tuple.

## 2. Root tests/conftest.py env fixture + import ordering — CONFIRMED (mechanism verified)

- Autouse **session-scoped** fixture `setup_test_environment` at `tests/conftest.py:54-77`. Pins
  exactly: `GOOGLE_CLOUD_PROJECT=test-project`, `GOOGLE_CLOUD_LOCATION=us-central1`,
  `GCS_BUCKET=test-bucket`, `GOOGLE_GENAI_USE_VERTEXAI=True` (lines 59–64). Restores originals
  on teardown (lines 73–77). It is the only env fixture.
- **`app.config` is imported at conftest module top, before any fixture can run**:
  `tests/conftest.py:45` — `from app.config import DB_PATH as _CONFIG_DB_PATH`. Module-level
  values in `app.config` (`GCS_BUCKET`, `MODEL`, `DB_PATH`, …) are therefore evaluated from the
  developer's real environment at collection time; the session fixture's pins only reach code
  that re-reads `os.environ` or reloads the module afterwards. This is the ws15 discovery,
  intact at current line numbers.
- Corollary for step 1's live conftest: any integration fixture restoring real env must either
  run before `app.config` import (impossible from a nested conftest — root conftest imports it
  at collection) or `importlib.reload(app.config)` after setting env — and must handle the
  reload side effects described in item 6 below.
- Other relevant fixtures: `test_db` (function, DB copy, patches `app.config.DB_PATH`,
  lines 115–134), `shared_test_db` (module, 137–152), `fresh_test_db` (155–176), `empty_test_db`
  (Phase 15 schema-only, 179–198), `mock_gcs_storage` (205–223), `mock_storage_module` (226–241,
  patches all `app.storage` helpers including ws15's `product_image_exists` /
  `get_product_image_public_url`).

## 3. Open item 6 (combined-run GCS state leak) — CONFIRMED and REPRODUCED

Reloader cleanup lines:

- `tests/unit/test_config.py:10-15` — autouse fixture:
  ```python
  @pytest.fixture(autouse=True)
  def _reload_config_after_test(monkeypatch):
      """Each test reloads app.config; re-reload under the restored env afterwards."""
      yield
      monkeypatch.undo()
      importlib.reload(config_module)
  ```
  The final `importlib.reload(config_module)` runs with the session fixture's
  `GCS_BUCKET=test-bucket` still in `os.environ` ("restored env" = restored *monkeypatch* env,
  which still includes the session pins) — flipping `app.config.GCS_BUCKET` from `None` to
  `"test-bucket"` for the rest of the process.
- `tests/unit/test_demo_dataset_gate.py:19-20` — inline cleanup in
  `test_invalid_value_raises_at_load`:
  ```python
  monkeypatch.delenv("DEMO_DATASET")
  importlib.reload(app.config)  # restore clean module state for later tests
  ```
  Same mechanism.

Affected e2e tests (exact defs): `tests/e2e/test_demo_workflows.py:190`
(`test_video_review_table`), `:323` (`test_campaign_map_data`), `:428`
(`test_product_then_review_flow`). All three call tools that reach
`app.storage.get_product_image_public_url` → `product_image_exists` → real
`google.cloud.storage` when `app.config.GCS_BUCKET` is truthy (storage reads config at call
time, `app/storage.py:47,61`).

**Reproduction (this worktree has a `.venv`, Python 3.14):**

```
.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_demo_dataset_gate.py tests/e2e -x -q
→ 1 failed, 23 passed in 10.28s
FAILED tests/e2e/test_demo_workflows.py::TestHITLReviewWorkflow::test_video_review_table
google.api_core.exceptions.Forbidden: 403 GET https://storage.googleapis.com/storage/v1/b/test-bucket/o/product-images%2Fblue-floral-maxi-dress.png ...
  lavinigam@aicloudadvocacy.joonix.net does not have storage.objects.get access ...
```

Exactly the predicted failure: a **real network call to bucket `test-bucket`** using local ADC
credentials, from the first of the three e2e tests, in the combined-run ordering only. (The
split `make test-unit` / `make test-e2e` targets are separate processes and stay green — not
re-run here, but the mechanism requires same-process ordering.)

## 4. Makefile — CONFIRMED (incl. no test-live; reset-db echo stale as claimed)

Verbatim (tabs elided), `Makefile`:

- `test` (line 172): `test: test-unit test-integration` then `@echo "All tests passed!"` —
  **integration is currently IN the default target** (step 6 will move it out).
- `test-unit` (177–183): `pytest tests/unit -v --tb=short` (venv-aware).
- `test-integration` (186–192): `pytest tests/integration -v --tb=short -m "not slow"`.
- `test-e2e` (195–201): `pytest tests/e2e -v --tb=short`.
- `test-all` (204–210): `pytest tests/ -v --tb=short`.
- `test-coverage` (213–221): `pytest tests/ --cov=app --cov-report=html --cov-report=term-missing`
  (single process over all of tests/ — poisoned by item 6, as the phase doc says).
- `reset-db` (256–264): deletes `campaigns.db` + `app/campaigns.db`; echo text lines 262–264:
  `"  - 4 demo campaigns (LA, NYC, Chicago)"`, `"  - 22 fashion products"`, `"  - 1 activated
  video per campaign with 30 days of metrics"`. **Stale as claimed** — actual fashion dataset
  seeds 28 products (22 fashion + 6 retail core, asserted at
  `tests/unit/test_demo_dataset_gate.py:50`) and is `DEMO_DATASET`-dependent.
- **No `test-live` target** (`grep -n "test-live" Makefile` → nothing). `help` TESTING block at
  lines 301–307 describes the current 5 targets only.

## 5. app/config.py — CONFIRMED (model flip already done, per ws14 amendment)

- `MODEL = os.environ.get("AGENT_MODEL", "gemini-3.6-flash")` — `app/config.py:64`. Step 3 is
  indeed a no-op re-verification.
- `IMAGE_GENERATION = os.environ.get("IMAGE_GENERATION_MODEL", "gemini-3-pro-image")` — line 70.
- `VIDEO_GEN_MODEL = os.environ.get("VIDEO_GEN_MODEL", "veo-3.1-generate-001")` — line 71.
- `APP_MODE`: StrEnum `AppMode` (demo|connected) lines 27–39; unset/empty → DEMO; invalid →
  ValueError at import. `DEMO_DATASET`: StrEnum (fashion|none) lines 45–57, same pattern.
- `GCS_BUCKET = os.environ.get("GCS_BUCKET") or None` — line 94 (explicit opt-in; unset = local).
- `LOCAL_ASSETS_DIR` block lines 105–112: `LOCAL_ASSETS_DIR = os.environ.get("LOCAL_ASSETS_DIR")
  or PROJECT_DIR`; `SELECTED_DIR`, `GENERATED_DIR`, `PRODUCT_IMAGES_DIR` all join under it
  (lines 110–112).
- `DB_PATH` selection lines 118–128 (Agent Engine /tmp, Cloud Run app/, else project root).
- Also relevant: `VIDEO_ASPECT_RATIO = "9:16"` (74), `VIDEO_DURATION_SECONDS = 8` (75).

## 6. Storage/URL policy surface (app/storage.py) — CONFIRMED

- Public URL construction is centralized: `get_public_url(blob_path)` at `app/storage.py:354-369`
  returns `https://storage.googleapis.com/{GCS_BUCKET}/{blob_path}` or **None when GCS_BUCKET
  unset** — so local mode structurally cannot emit storage URLs.
- Wrappers: `get_video_public_url` (372–384, `check_exists=False` default),
  `get_thumbnail_public_url` (387–395, `check_exists=True` default, "ws09 bar" docstring),
  **ws15's existence-checked product-image helper `get_product_image_public_url`**
  (398–408): returns None unless GCS mode AND (by default) `product_image_exists(filename)`.
- Local landing dirs: `save_image` → `SELECTED_DIR` (148–152); `save_video` → `GENERATED_DIR`
  (251–255); `save_product_image` → `PRODUCT_IMAGES_DIR` (212–216). Mode detection:
  `get_storage_mode()` (55–62) reads `config.GCS_BUCKET` at call time (hence item 6's leak).
- What a "no storage.googleapis.com URL in tool responses" live assertion looks like already
  exists as a unit-level pattern: `tests/unit/test_url_policy.py` (docstring lines 1–4: "ws09
  bar: tool responses never emit storage.googleapis.com in local mode, and GCS-mode URLs are
  existence-checked") asserts `"storage.googleapis.com" not in json.dumps(result)` over
  `list_products`, `get_video_review_table`, `get_video_details`, with a `local_mode` fixture
  that monkeypatches `app.config.GCS_BUCKET = None`. The live tier can reuse this exact
  assertion shape against live tool responses.

## 7. Judge rubric inputs (ws09 archetype registry + ad-style policy) — CONFIRMED

- **Archetype registry**: `app/tools/prompt_archetypes.py`. Archetype constants lines 11–14
  (`WEARABLE`, `CONSUMABLE_HERO = "consumable-hero"`, `STAGED_PRODUCT = "staged-product"`,
  `PRODUCT_HERO = "product-hero"`). `ARCHETYPE_BY_CATEGORY` dict lines 16–24: fashion categories
  (dress/top/pants/skirt/outerwear/footwear) → wearable; beverage, qsr-menu-item →
  consumable-hero; electronics, furniture, home-appliance → staged-product; unknown categories
  fall back to product-hero. `resolve_archetype(product, variation)` lines 27–51:
  `presentation_mode` auto/product_only/with_model semantics; `with_model` on a non-wearable
  raises ValueError (lines 41–48) — the "cans-dress bug" guard the exit criteria references.
- **No-text/no-badge policy wording**: `app/tools/prompt_builders.py:32-40`:
  ```
  # clean frame — no rendered text and no spoken audio, for every archetype.
  _NO_TEXT_BLOCK = """NO TEXT OR GRAPHICS:
  - Do NOT render any text, words, numbers, labels, badges, captions, watermarks, or graphic overlays anywhere in the frame
  - The only text allowed is text that is physically part of the product's own packaging or label"""

  _AUDIO_BLOCK = """AUDIO & ON-SCREEN TEXT:
  ...
  - No on-screen text, captions, subtitles, titles, badges, or graphic overlays"""
  ```
  `_NO_TEXT_BLOCK` is interpolated into image prompts at lines 213 and 558; product-fidelity
  wording ("Do NOT alter, modify, or reinterpret the product design, packaging, or logo") at
  line 550. These are the direct rubric sources for step 5's judge.

## 8. Existing slow/veo/integration coverage — gathered

Markers declared in `pytest.ini:27-31`: `slow`, `integration`, `veo`, `e2e`.

- `tests/integration/test_agents.py` — whole module `pytest.mark.integration` (line 39); the
  `TestAllEvalSets.test_all_eval_sets_multi_run` is additionally `slow` (line 169). All vacuous
  under pytest today (Q19).
- `tests/unit/test_video_tools.py:286-287` — `@pytest.mark.slow @pytest.mark.veo` on class
  `TestVideoGenerationIntegration`. **Caveat: despite the veo marker, its tests mock
  `animate_scene_with_veo` and `generate_scene_image`** (lines 292–300) — it does not actually
  hit Veo. The markers over-claim; live tier should not count this as live coverage.
- `tests/e2e/test_demo_workflows.py:146-147` — `slow` + `veo` on `test_video_generation_flow`
  ("requires Veo API" docstring) but it takes `mock_storage_module`; `:298` `slow`
  `test_chart_generation` (real `generate_metrics_visualization` image-model call, accepts
  success OR clean error dict); `:364` `slow` `test_map_visualization`.
- Net: **nothing today genuinely asserts on live Veo/image output**; the only real-API-capable
  test (`test_chart_generation`) passes on error dicts too. Step 4/5 are green-field.

## 9. ws14 WORK_LOG candidate eval cases — verbatim

`.docs/version2-plan/working-docs/14-model-upgrades/WORK_LOG.md:147-151`:

> Observations (non-blocking, candidate Phase 16 eval cases): cold-start
> "create campaign for \<product\>" without a prior list_products led the agent
> to create_product a duplicate instead of resolving the seeded id (verifier
> cleaned up; correct after listing first); legacy variation fields
> (model_ethnicity/activity) still in saved variation JSON — cosmetic only.

Two cases: (1) cold-start create-campaign should resolve the existing seeded product id, not
`create_product` a duplicate; (2) legacy variation fields (`model_ethnicity`/`activity`)
persisting in saved variation JSON.

Adjacent Q14/Q15 evidence (same file, lines ~139–146) for open item 5:
gemini-3-pro-image product image 1408x768 PNG ~866KB; Veo 3.1 8.0s 720x1280 24fps h264+aac
~2.3–3.3MB; Omni probe 4s/24fps/720p-class ~1.0–1.1MB, ~30s end-to-end vs Veo ~60–130s.

## 10. ws10 carried item 4 (repo-wide lint) — CONFIRMED, current count 42

Recorded at `.docs/version2-plan/working-docs/10-playout-attribution/WORK_LOG.md:108`:

> 4. Repo-wide `make lint` is red with ~40 pre-existing errors (predates ws10; ws10 added zero
> and removed one) — needs a dedicated cleanup slot so lint can become a real gate.

Current state (`make lint` in this worktree): **Found 42 errors, 30 fixable with `--fix`**
(7 more with `--unsafe-fixes`). Category breakdown (`ruff check app tests --statistics`):
I001 unsorted-imports ×11, UP042 replace-str-enum ×7, F541 f-string-missing-placeholders ×6,
UP045 non-pep604-annotation-optional ×6, UP006 non-pep585-annotation ×5, UP035
deprecated-import ×4, F401 unused-import ×3.

## 11. docs/demo-scenarios/ — CONFIRMED

Exactly two scenario files: `docs/demo-scenarios/fashion.md` and
`docs/demo-scenarios/from-scratch-onboarding.md` (open item 3's referenced file exists).

## 12. scripts/demo_assets.py mechanism — CONFIRMED

- `MARKER_NAME = ".demo-assets-installed"` — `scripts/demo_assets.py:42`.
- `_sha256(data)` → `"sha256:" + hashlib.sha256(...).hexdigest()` — line 46.
- `build_bundle(source_dir, out_path)` — line 50 (per-file sha256 manifest.json, line 62).
- `verify_and_extract(zip_path, dest_dir)` — line 69; raises ValueError on missing manifest,
  count mismatch, or sha256 mismatch (line 92).
- `_download_from_drive(drive_id, out_path)` — lines 101–103, lazy `import gdown`,
  `gdown.download(id=drive_id, ...)`.
- `install(from_file=None, dest_dir=None)` — lines 106–131: marker no-op check at 108–111
  (`{"status": "skipped", ... Delete the marker to force reinstall}`); `DEMO_ASSETS_DRIVE_ID`
  graceful-skip at 117–121 ("the app works without it; seeded products will show
  image_status=missing locally"); download → `verify_and_extract` → marker written with
  `BUNDLE_VERSION` + `installed_count` (127–129). Dest defaults to `LOCAL_ASSETS_DIR`.
- Matches open item 1's description exactly; only the Drive-download leg is unproven live.

## 13. Q19 + CLAUDE.md gotcha (targets of open item 4's rewrite) — located

- **Q19**: `.docs/version2-plan/99-open-questions.md:122` — heading "## 19. Integration eval
  suite: vacuous under pytest, and eval sets fail when genuinely run (discovered workstream 09,
  2026-07-22) — RESOLVED 2026-07-22". Body (lines 124–132): resolution paragraph ("full live
  repair — option (a), expanded", owner quote "We should have both fast test and full test with
  live api and both should pass. dont worry about the cost.", scoped as Phase 16), then the
  two-problem mechanism (fake project → 403 → LocalEvalService swallows → metric-only failure
  counting; genuinely-run sets fail on direct-tool-call trajectories + response_match ≈ 0), then
  repair options (a)/(b) with the note that ws09 shipped Task 7 eval cases "documented as
  unexercised, per (b) pending the decision". Item 4's rewrite should convert the historical
  record to "resolved by Phase 16 shipping" once step 1 lands.
- **CLAUDE.md gotcha**: worktree `CLAUDE.md:80`, the single bullet beginning "**The integration
  eval suite passes vacuously under pytest** (discovered workstream 09, 2026-07-22): …" ending
  "…see `99-open-questions.md` Q19 for the repair options." Becomes wrong the moment step 1
  ships, as the phase doc says.

---

## Additional environment facts for the working doc

- **Worktree has its own `.venv` (Python 3.14** per `.venv/lib/python3.14/` in tracebacks) —
  test commands run in-place. Reminder: Agent Engine deploys need ≤3.13, irrelevant for tests.
- **`app/.env` is NOT present in this worktree** (untracked files don't follow worktrees); the
  main checkout has `/Users/lavi/gwork/video-ad-optimization-agent/app/.env` (139 bytes). The
  live tier's "restore real env from app/.env" fixture needs the file copied/symlinked into the
  worktree (and note open item 2(a): a dev `.env` with `GCS_BUCKET` set silently keeps GCS mode).
- **Local ADC credentials are live** (`lavinigam@aicloudadvocacy.joonix.net` per the reproduced
  403) — real Vertex/GCS calls from tests will authenticate.
- **agents-cli installed: version 1.1.0** at `/Users/lavi/.local/bin/agents-cli` (execution
  directive 3 requires a latest-version check/upgrade at kickoff — not performed here; do it in
  the kickoff step with July-2026-current sources).
- Eval-set reference-response landmine for step 2: 3 of 4 campaign_agent cases (and, by the same
  authoring pattern, most cases in the other four sets) carry **empty-string** reference
  responses — `response_match_score` against "" is meaningless, supporting the phase doc's
  "response-match relaxed or dropped" recommendation; the directive-2 answer-correctness
  dimension will need newly authored references (owner input per directive 6).
- `make test-coverage` and any single-process `pytest tests` run are currently broken by item 6
  on credentialed machines (reproduced above); the split Make targets are the only green path
  today.
