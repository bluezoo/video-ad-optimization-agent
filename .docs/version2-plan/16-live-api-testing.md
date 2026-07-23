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
2. **Repair the eval sets so they can genuinely pass.** All five
   `tests/integration/eval_sets/*.test.json` expected trajectories currently
   pin direct tool calls, but the coordinator's real trajectory wraps them in
   `transfer_to_agent` (confirmed live, ws09) and `response_match_score` ≈ 0
   against the pinned reference responses. Rewrite expected trajectories to
   the real shape and add a `test_config.json` criteria file (tool-trajectory
   weighted; response-match relaxed or dropped — these are routing tests, not
   wording tests). Calibrate against live runs.
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
6. **Make targets and defaults.** `make test` stays fast-by-default (unit +
   e2e; integration moves OUT of the default target so the everyday loop
   spends no LLM calls); `make test-live` = repaired integration evals + live
   media tests + judge; `make test-all` includes both tiers. Document the cost
   profile in CLAUDE.md (owner: cost is accepted — correctness first).

## Validation

- [ ] Deliberate-break check finally works: corrupting an eval set's expected
      tool name makes `make test-live` FAIL (the ws09 check that exposed the
      vacuity), and reverting it passes.
- [ ] The vacuity guard turns "zero inferences ran" into a loud failure, never
      a pass.
- [ ] `make test-live` passes end-to-end on `gemini-3.6-flash` + Veo + the
      image model, including judge verdicts on freshly generated media.
- [ ] `make test` (fast tier) still runs in seconds with zero LLM calls.

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
2. Audio verification: Veo output audio can't be fully verified by a
   frame-based judge; is prompt-policy + spot manual listening acceptable, or
   is an audio-understanding pass (Gemini video+audio input) worth adding?

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
3. **From-scratch onboarding as a live test case (ws15).** `DEMO_DATASET=none`
   → `create_product` → `generate_product_image` against the real image
   model → campaign attach — the
   `docs/demo-scenarios/from-scratch-onboarding.md` path, currently proven
   only by manual verification. Run the generated image through the step-5
   judge like any other media output.
4. **Docs/targets cleanup once the tier lands.** Rewrite the CLAUDE.md
   "integration eval suite passes vacuously" gotcha (it becomes wrong the
   moment step 1 ships), update `make help`/`make test` descriptions for the
   new tier split, and fix the stale `reset-db` echo text ("22 fashion
   products" — dataset is now `DEMO_DATASET`-dependent).
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
