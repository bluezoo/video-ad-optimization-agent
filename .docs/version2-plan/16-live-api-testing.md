# Phase 16 — Live-API Test Tier (fast tests + full live tests, both green)

> **New phase (workstream 09, 2026-07-22), from an owner directive after manual
> testing.** Verbatim intent: "why does the test not use live api? … we have
> vertex and it should do live test and see the outputs. you can change the
> model to 3.6 flash which is new and it should hit the veo and nano banana as
> well. you should also write a script in test that can use gemini 3.6 flash to
> review the images and video, so that we know what we are getting is expected
> or not. We should have both fast test and full test with live api and both
> should pass. dont worry about the cost. its important to keep things correct."
> This phase is the resolution of open question **Q19** (the integration eval
> suite passes vacuously under pytest — see `99-open-questions.md` and the ws09
> WORK_LOG DISCOVERY for the pinned mechanism).

## Goal

Two test tiers, both green and both honest:

- **Fast tier** (unchanged behavior, no LLM calls): `make test-unit` + `make
  test-e2e` — seconds, runs on every edit (PostToolUse hook).
- **Live tier** (new, real Vertex APIs): a `make test-live` target that (a)
  genuinely executes the agent-routing eval sets against the live LLM, (b)
  generates real media through the two-stage pipeline (image model + Veo), and
  (c) has a **Gemini-judge** review the generated images/videos so we know the
  outputs match expectations — not just that the calls returned 200.

## Steps

1. **Un-vacuous the integration suite (Q19 repair).** A
   `tests/integration/conftest.py` fixture restores the real environment (from
   `app/.env`) per integration test, overriding the root conftest's fake
   `GOOGLE_CLOUD_PROJECT=test-project` (which stays — unit tests need it);
   plus a **vacuity guard**: capture ADK's `local_eval_service` logger during
   each eval run and FAIL (or xfail as infrastructure, per the narrowed
   `_INFRA_MARKERS`) when inference errors were swallowed — a "pass" with zero
   real inferences must be impossible.

   > **Amended (workstream 16, 2026-07-23):** done, but not as sketched — the
   > logger-capture approach was superseded before implementation. The actual
   > vacuity was traced to `AgentEvaluator.evaluate_eval_set`'s pytest
   > aggregation, which compares only mean metric scores and never inspects
   > per-case `final_eval_status` (not a `LocalEvalService` bug — it already
   > records `InferenceStatus.FAILURE` correctly per case). The shipped fix
   > (`tests/integration/eval_harness.py`) asserts per-case `final_eval_status`
   > directly (`assert_eval_outcomes`) instead of scraping a logger — a
   > structural check, not a log-scrape, and superior to the sketch (no
   > reliance on log message text staying stable across ADK versions). See the
   > CLAUDE.md Gotchas rewrite for the full mechanism and `99-open-questions.md`
   > Q19 for the resolution record.
2. **Repair the eval sets so they can genuinely pass.** All five
   `tests/integration/eval_sets/*.test.json` expected trajectories currently
   pin direct tool calls, but the coordinator's real trajectory wraps them in
   `transfer_to_agent` (confirmed live, ws09) and `response_match_score` ≈ 0
   against the pinned reference responses. Rewrite expected trajectories to
   the real shape and add a `test_config.json` criteria file (tool-trajectory
   weighted; response-match relaxed or dropped — these are routing tests, not
   wording tests). Calibrate against live runs.

   > **Amended (workstream 16, 2026-07-23):** done — all five eval sets
   > (`coordinator`, `campaign_agent`, `media_agent`, `analytics_agent`,
   > `review_agent`) repaired to the real `transfer_to_agent`-wrapped
   > trajectories (Tasks 6–10, `.superpowers/sdd/progress.md`), calibrated
   > against `OWNER_REVIEW.md`'s live actuals (OWNER GATE 1) rather than a
   > relaxed/dropped response-match — `final_response_match_v2` (LLM judge)
   > runs as the harness's third dimension per execution directive 2, not
   > "relaxed or dropped" as originally sketched.
3. **Default model → `gemini-3.6-flash`.** Change `MODEL` in `app/config.py`
   (stays env-overridable via `AGENT_MODEL`); verify the
   `GOOGLE_CLOUD_LOCATION=global` constraint still holds for 3.6 and update
   the CLAUDE.md gotcha if the constraint changed. Fast + live suites both
   pass on the new default.

   > **Amended (workstream 14, 2026-07-22):** done here — default flipped to
   > `gemini-3.6-flash` (GA 2026-07-21, verified live on Vertex `global` at
   > ws14 kickoff; CLAUDE.md gotcha unchanged). Phase 16 keeps this step only
   > as a no-op re-verification when the live tier lands.
4. **Live media-generation tests.** Fold/extend the existing `slow`/`veo`
   markers into the live tier: a test that runs the two-stage pipeline for one
   wearable and one non-wearable (retail core set) end-to-end against the real
   image model ("nano banana" per Phase 14a) and Veo, asserting the tool
   contract (status success, artifact saved, `reference_image_used` honest,
   product-centric vs fashion filename per archetype).

   > **Amended (workstream 16, 2026-07-23):** done — `tests/live/test_media_pipeline.py`
   > (Task 12), one wearable (blue-floral-maxi-dress) and one non-wearable
   > retail-core (aurora-cold-brew-330ml) case, both asserted against the real
   > tool contract; a from-scratch onboarding image-generation case
   > (Task 13, `tests/live/test_onboarding_from_scratch.py`) added beyond the
   > original scope, closing "Open items" #3 below. Recorded resolution
   > evidence for Q14/Q15 in
   > `.docs/version2-plan/working-docs/16-live-api-testing/calibration/media-metadata.json`.
5. **Gemini-judge review script.** A test-side judge (e.g.
   `tests/live/judge.py`) that feeds each generated image/video to
   `gemini-3.6-flash` (multimodal) with a structured rubric derived from the
   ws09 ad-style policy and archetype expectations, returning per-check
   verdicts the tests assert on: correct subject for the archetype (product
   hero for non-wearables — no humans in `product_only` output; model wearing
   the garment for wearables), **no rendered text/badges/overlays in the
   frame** (beyond the product's own packaging), setting/mood plausibly match
   the request, and for videos: no visible captions/titles (audio speech
   detection is best-effort — assert via the prompt policy plus judge review
   of frames; note limitations in the rubric rather than over-claiming).

   > **Amended (workstream 16, 2026-07-23):** done — `tests/live/judge.py`
   > (Task 14), owner-approved severities (OWNER GATE 2: hard =
   > `subject_matches_archetype`, `no_rendered_text`, `no_captions_any_frame`,
   > both chart checks; warn = `setting_mood_plausible` — resolves phase-doc
   > Open question 1 below), negative controls proven to fail (rendered-text
   > overlay, wrong-subject), subject rule for product-hero relaxed to "no
   > *featured* human model" (OWNER GATE 3 — incidental/blurred background
   > people allowed), and a bounded one-shot media re-judge on any hard-check
   > failure (OWNER GATE 4, same file, no regeneration). Audio genuinely NOT
   > verified — the rubric says so explicitly, matching phase-doc Open
   > question 2's "prompt-policy + no audio-understanding pass" option (see
   > below).
6. **Make targets and defaults.** `make test` stays fast-by-default (unit +
   e2e; integration moves OUT of the default target so the everyday loop
   spends no LLM calls); `make test-live` = repaired integration evals + live
   media tests + judge; `make test-all` includes both tiers. Document the cost
   profile in CLAUDE.md (owner: cost is accepted — correctness first).

   > **Amended (workstream 16, 2026-07-23):** done — `make test` = unit + e2e
   > only (Task 3); `make test-live` = `pytest tests/integration tests/live`
   > with an `app/.env` presence guard (Task 4); `make test-all` still covers
   > `tests/` unchanged, which structurally includes both tiers. CLAUDE.md's
   > Gotchas section carries the cost note verbatim ("owner: cost accepted,
   > correctness first") and the tier map. An informational
   > `make test-live-report` (agents-cli grading layer, Task 15) was added
   > beyond the original step's scope — explicitly not a gate.

## Validation

- [x] Deliberate-break check finally works: corrupting an eval set's expected
      tool name makes `make test-live` FAIL (the ws09 check that exposed the
      vacuity), and reverting it passes.
      > **Amended (workstream 16, 2026-07-23):** verified — Task 6's
      > `list_campaigns` → `list_campaignsX` deliberate break made the
      > coordinator case FAIL on tools=0.0 and trajectory=0.0; reverting
      > passed again (`.superpowers/sdd/progress.md`, Task 6 entry).
- [x] The vacuity guard turns "zero inferences ran" into a loud failure, never
      a pass.
      > **Amended (workstream 16, 2026-07-23):** done via `_assert_isolated_db`
      > + per-case `final_eval_status` assertion in `assert_eval_outcomes`
      > (see step 1's amendment) — an inference failure now fails the pytest
      > run, it cannot pass silently.
- [x] `make test-live` passes end-to-end on `gemini-3.6-flash` + Veo + the
      image model, including judge verdicts on freshly generated media.
      > **Amended (workstream 16, 2026-07-23):** verified — full `make
      > test-live` = 26 passed / 0 failed in 673.84s (11m13s), post-GATE-4
      > (`.superpowers/sdd/progress.md`, Task 14 completion entry).
- [x] `make test` (fast tier) still runs in seconds with zero LLM calls.
      > **Amended (workstream 16, 2026-07-23):** verified throughout —
      > `make test` (unit + e2e) stayed green at every checkpoint (319–344
      > passed depending on stage), seconds, no network calls.

## Exit criteria

Both tiers green on a clean checkout with real `app/.env`: fast tier in
seconds with no network, live tier genuinely exercising routing, generation,
and judge-reviewed output quality — so a routing or prompt regression (e.g.
the cans-dress bug, text badges in frame) is caught by CI-runnable tests, not
only by manual demos.

## Dependencies

Phase 9 (archetype registry + ad-style policy — the judge's rubric asserts
them). Independent of Phases 10-15; sequence early — every later phase
benefits from a truthful live gate.

## Open questions

1. Judge reliability: what agreement threshold before a judge verdict blocks
   (vs warns)? Default: hard-fail on rendered-text and wrong-subject checks,
   warn-only on subjective mood/setting checks, revisit after a few runs.

   > **Answered (OWNER GATE 2, workstream 16, 2026-07-23):** default proposal
   > approved as-is — hard: `subject_matches_archetype`, `no_rendered_text`,
   > `no_captions_any_frame` (video), both chart checks
   > (`axes_and_labels_legible`, `correct_creative_count`); warn:
   > `setting_mood_plausible`. Revisited once, at OWNER GATE 3 (2026-07-23):
   > the product-hero `subject_matches_archetype` rule was relaxed from "no
   > people in background" to "no *featured* human model" after a
   > false-positive on ambient background blur — negative controls (rendered
   > text, wrong subject) still fail correctly under the relaxed rule. See
   > `working-docs/16-live-api-testing/WORK_LOG.md`'s OWNER GATE 2/3 entries.
2. Audio verification: Veo output audio can't be fully verified by a
   frame-based judge; is prompt-policy + spot manual listening acceptable, or
   is an audio-understanding pass (Gemini video+audio input) worth adding?

   > **Answered (workstream 16, 2026-07-23):** shipped as prompt-policy +
   > frame-based judge only, no audio-understanding pass — `tests/live/judge.py`
   > judges burned-in captions per sampled/decoded frame and states in its
   > rubric that audio itself is not verified (music-only/no-voiceover is
   > enforced by the prompt policy, `_AUDIO_BLOCK`, not checked post-hoc). No
   > owner ask for an audio-understanding pass surfaced during the workstream;
   > this stays open if a future regression specifically implicates audio
   > content rather than the burned-in-caption/text policy this tier already
   > covers.

## Open items to address while testing

> **Amended (owner request, 2026-07-22, post-ws15 merge):** carried-in items
> from merged workstreams that this phase's live testing is the natural place
> to close. The doc's original "Independent of Phases 10-15" note predates
> ws15's merge — item 2 below supersedes it for storage behavior.

1. **Publish and live-verify the demo-asset bundle (ws15 owner follow-up).**
   Only the graceful-skip path is proven live today. Close the loop:
   `make demo-assets-build SRC=<folder>` → upload zip to Google Drive
   (anyone-with-link) → set `DEMO_ASSETS_DRIVE_ID` in `app/.env` → verify a
   first `make dev` (or `make demo-assets`) downloads, sha256-verifies, and
   installs into `product-images/`, and a second run is a marker no-op.
   Seeded products should then report `image_status: available` locally.

   > **Amended (workstream 16, 2026-07-23, OWNER GATE 5):** DEFERRED by the
   > owner — no asset source folder exists yet (the owner supplies it), so
   > publishing stays an owner follow-up exactly as SETUP_INSTRUCTIONS.md
   > documents it. The build/verify/install code remains covered by ws15's
   > `test_demo_assets` (6/6) and the graceful "bundle not configured" skip.
2. **Pin the live tier's storage mode and assert the URL policy (ws15).**
   Decide which storage mode live tests run in — recommend local-first
   (`GCS_BUCKET` unset), matching the demo default. Assert the ws09
   directive as a test: no `storage.googleapis.com` URL in any tool
   response, and generated media lands under `LOCAL_ASSETS_DIR`
   (`generated/`, `selected/`, `product-images/`). Two known env landmines
   for step 1's integration conftest: (a) a dev `app/.env` that still sets
   `GCS_BUCKET` silently keeps GCS mode; (b) the root conftest's
   session-scoped env fixture runs AFTER `app.config` is imported, so env
   pins set there never reach module-level config values (ws15 discovery) —
   the live-tier conftest must set env before `app.config` import or reload
   the module.

   > **Resolved (workstream 16, 2026-07-23):** local-first, no exceptions —
   > `tests/integration/conftest.py` force-unsets `GCS_BUCKET`
   > (`LIVE_ENV_UNSET = ("GCS_BUCKET",)`) for the whole live tier regardless
   > of what a dev's `app/.env` sets, and asserts `config_module.GCS_BUCKET
   > is None`. There is no `storage.googleapis.com` reference anywhere in the
   > live tier's results, verified across every `make test-live` run this
   > workstream. Both landmines were hit and fixed during Tasks 1–5 (see
   > `.superpowers/sdd/progress.md`).
3. **From-scratch onboarding as a live test case (ws15).** `DEMO_DATASET=none`
   → `create_product` → `generate_product_image` against the real image
   model → campaign attach — the
   `docs/demo-scenarios/from-scratch-onboarding.md` path, currently proven
   only by manual verification. Run the generated image through the step-5
   judge like any other media output.

   > **Done (workstream 16, 2026-07-23, Task 13):**
   > `tests/live/test_onboarding_from_scratch.py` — a non-fashion product
   > (Artisan Coffee Beans) on a schema-only empty DB: `create_product`
   > (pending) → `generate_product_image` via the real image model →
   > `create_campaign` attach, no `storage.googleapis.com` anywhere; the
   > generated image is registered in `generated_media` so Task 14's judge
   > reviews it like any other media output (it does — the judge passed it).
4. **Docs/targets cleanup once the tier lands.** Rewrite the CLAUDE.md
   "integration eval suite passes vacuously" gotcha (it becomes wrong the
   moment step 1 ships), update `make help`/`make test` descriptions for the
   new tier split, and fix the stale `reset-db` echo text ("22 fashion
   products" — dataset is now `DEMO_DATASET`-dependent).

   > **Done (workstream 16, 2026-07-23, Task 16 — this cleanup pass):**
   > CLAUDE.md's gotcha rewritten with the refined mechanism (see the
   > "Gotchas" section) and a tier map added to "Commands"; `reset-db`'s
   > echo text updated in the `Makefile` (now "28 products (22 fashion +
   > 6 retail core), DEMO_DATASET-dependent" — verified against
   > `app/database/products_data.py` (22) + `retail_products_data.py` (6)).
   > `make help`'s `test-integration`/`test-live`/`test-live-report` lines
   > shipped earlier in this workstream (Tasks 3 and 15) and were verified
   > current here.
5. **Opportunistic evidence for Q14/Q15 while paying for the calls.** Live
   media runs should record actual image resolutions (Q14, Phase 14a) and
   qualitative video-output notes (Q15, Phase 14b) into the workstream's
   WORK_LOG — free input for those open questions, no extra API spend.
6. **Fix the combined-run GCS state leak (found post-ws15 merge, 2026-07-23
   review).** In a single-process run spanning unit + e2e (`pytest tests`,
   `make test-coverage` — NOT the split `make test-unit`/`test-e2e`, which
   stay green), `tests/unit/test_config.py` and
   `tests/unit/test_demo_dataset_gate.py`'s cleanup
   `importlib.reload(app.config)` executes under the root conftest's
   session-pinned `GCS_BUCKET=test-bucket`, permanently flipping
   `app.config.GCS_BUCKET` from None to `"test-bucket"` for the rest of the
   process. `app/storage.py` reads config at call time, so three e2e tests
   whose tools hit ws15's existence-checked product-image URL helper
   (`get_video_review_table`, `get_campaign_map_data`,
   `test_product_then_review_flow`) then issue real
   `google.cloud.storage` requests (fail on machines with ADC credentials;
   would also poison the coverage target). Same root cause family as item
   2(b): reload-vs-session-env ordering. Fix candidates: make both
   reloaders' final reload run under a scrubbed env (monkeypatch delenv
   GCS_BUCKET before the restore reload), or have the session fixture pin
   `app.config.GCS_BUCKET` as a module attribute too, so reloads can't
   drift from what tests were promised.

   > **Done (workstream 16, 2026-07-23, Task 2, commit `3aa9c7e`):** fixed via
   > the first fix candidate's spirit, refined — `tests/_config_baseline.py`
   > snapshots `app.config`'s import-time state and a `restore_config_baseline()`
   > helper restores it exactly (no reload, no env reads) instead of a second
   > `importlib.reload` that would re-derive under whatever env is pinned at
   > cleanup time. Combined unit+e2e run was 3 failed/1 skipped before the
   > fix, 341 passed/2 skipped after.

## Execution directives (owner, 2026-07-23) — binding for this workstream

> **Amended (owner directive, 2026-07-23, pre-kickoff):** how this workstream
> must run, not just what it must build. These are process constraints on the
> same level as the working-doc/plan gates — deviations need explicit owner
> approval.

1. **Coverage bar: everything, output-validated.** The live tier must look at
   ALL changes merged across ws01–ws15 (archetype prompts, ad-style policy,
   attribution join, provider seam, onboarding, local-first storage, model
   defaults) and give each a test that validates the OUTPUT, not merely that
   the call ran: judge scripts analyze generated videos and images against
   rubrics, and agent-answer checks assert the response content is what a
   user should get. "It returned 200" is never a pass criterion by itself.
2. **Agent evals on three explicit dimensions.** For every eval case: (a) were
   the proper tool calls made, (b) was the trajectory correct (routing,
   ordering, transfer_to_agent wrapping), (c) is the received answer the
   expected one. Cases must be able to fail on each dimension independently.
3. **Toolchain: agents-cli is the eval-building system.** Use `agents-cli`
   (installed 1.1.0; verify/upgrade to the LATEST version at kickoff — it
   ships fast) as the core toolchain for this workstream: study its
   architecture first (`eval generate` / `grade` / `run` / `compare` /
   `metric`, experimental `dataset`/`analyze`/`optimize`), run
   `agents-cli setup` to install its ADK development skills into the coding
   agent, and use those skills both to CREATE the evals and to DIAGNOSE/FIX
   when something goes wrong. Survey what agents-cli can generate before
   hand-building anything — prefer its native formats/harness over bespoke
   scripts wherever they fit.
4. **Doc sources: July-2026-current only.** The core is ADK, so rely
   exclusively on: agents-cli core + its skills, the google-dev-knowledge
   MCP, and context7 (latest ADK docs). Fetch current docs for any ADK/eval
   API touched; never trust memory of older ADK behavior — if memory and the
   fetched docs disagree, the docs win. This applies to every subagent
   dispatched in this workstream, not just the controller.
5. **Incremental, not big-bang.** This is a big workstream: the plan must be
   staged so each step lands green and is committed before the next starts
   (constant commits at every fixed/passing increment). Build toward the end
   state step by step; no single mega-change, no long-lived uncommitted work.
6. **Never assume expected behavior — ask.** Whenever the expected agent
   response, judge verdict threshold, or output quality bar is unclear or
   ambiguous, STOP and ask the owner instead of assuming (e.g. "what should
   the agent's answer to X contain?"). Show the owner real outputs — agent
   answers AND generated media (images/videos or frame grabs) — and take
   their input before pinning expectations into eval cases or rubrics. Owner
   answers become the recorded expectation.
7. **Running log discipline.** Keep WORK_LOG.md continuously current as a
   running log this workstream re-reads whenever context is lost: every step
   taken, every fix, and EVERY owner decision/input (verbatim where short)
   logged at the moment it happens — the log is the reference of record for
   what was decided, so nothing rests on conversation memory. This is the
   most crucial workstream of the internal track; the log standard is
   accordingly higher, not lower.
