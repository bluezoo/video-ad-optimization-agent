# Workstream 16 — live-api-testing — WORK_LOG

Append-only running log. Per the owner's execution directive 7 (phase doc
§"Execution directives"), this log is kept **continuously current** — every
step, every fix, and every owner decision/input (verbatim where short) is
recorded at the moment it happens. It is the reference of record; nothing
rests on conversation memory.

## 2026-07-23 — checkpoint 1: kickoff — worktree created

- Branch `version_2_live-api-testing` off `version_2` @ f8df319 (verified:
  merge-base == version_2 HEAD). Worktree `.claude/worktrees/version_2_live-api-testing`.
- STATUS.md row 16 → `kickoff in progress` (main checkout, commit 3fc55d0).
- Phase doc read in full — three layers noted: original steps 1–6 (step 3
  already done in ws14, kept as no-op re-verification), 6 carried-in open
  items, and the **binding** "Execution directives (owner, 2026-07-23)"
  section (coverage bar = output-validated everything; 3-dimension evals;
  agents-cli as the eval-building toolchain; July-2026-current doc sources
  only; incremental commits; ask-don't-assume on expected behavior; this
  running-log discipline).
- Owner kickoff message (2026-07-23, verbatim constraints beyond the doc):
  upgrade agents-cli to latest + `agents-cli setup` + study its eval
  architecture and report what it can create BEFORE any working doc; fetch
  current ADK eval docs via context7 + google-dev-knowledge MCP only; plan
  as small incremental stages each committed when green; at the working-doc
  gate also propose whether the repo-wide lint cleanup (ws10 carried item 4)
  folds in; ws14 WORK_LOG has two candidate eval cases (cold-start duplicate
  create_product; legacy variation fields in saved JSON).
- Next: agents-cli upgrade/setup/study + doc fetch + phase-claim
  re-verification (kickoff research), then working doc.

## 2026-07-23 — kickoff research done (checkpoint 1 amendment)

- **agents-cli:** verified 1.1.0 IS the latest on PyPI (`uv tool upgrade` refreshed
  deps only); `agents-cli setup --workspace --skip-auth --agent claude-code` installed
  7 ADK skills into this worktree's `.claude/skills/` (committed 3fd4879):
  adk-code, deploy, **eval**, observability, publish, scaffold, workflow.
- **Research fan-out (4 parallel agents, ~720k tokens), reports committed under
  `research/`:**
  - `agents-cli-architecture.md` — full eval surface (generate/grade/run/compare/
    metric + experimental dataset synthesize/analyze/optimize/submit/results);
    17 built-in server-side LLM-judged metrics incl. separate tool-use /
    trajectory / task-success / final-response dimensions; **`eval generate`
    cannot run here today** (requires agents-cli-manifest.yaml + uv sync, repo
    has neither; hard 600s whole-dataset timeout would also break Veo cases;
    no DB isolation); **`eval grade` works project-free** (--traces --output
    --config) → hybrid recommended: our pytest live harness emits traces,
    agents-cli grades/compares. Custom LLMMetric (configurable judge model,
    multimodal per its skill's multimodal-eval.md) + CodeExecutionMetric
    available; GECKO_TEXT2IMAGE/TEXT2VIDEO exist but undocumented (spike-only).
  - `adk-eval-docs-context7.md` — current EvalSet/EvalCase schema (.test.json ≡
    .evalset.json); `tool_trajectory_avg_score` now supports
    `{threshold, match_type: EXACT|IN_ORDER|ANY_ORDER}`; `criteria` dict param
    DEPRECATED in favor of `eval_config=EvalConfig`; new judge-metric family
    (final_response_match_v2, rubric_based_{final_response,tool_use,
    multi_turn_trajectory}_quality_v1, hallucinations_v1, safety_v1, …).
    **Vacuity root cause refined from source:** LocalEvalService does NOT
    swallow failures — it sets InferenceStatus.FAILURE and
    final_eval_status=FAILED per case; the gap is AgentEvaluator's pytest
    aggregation, which only compares mean metric scores (empty when all
    inference failed) and never inspects final_eval_status → vacuity guard
    should assert on final_eval_status, not capture loggers (better than the
    phase doc's step-1 sketch). **transfer_to_agent confirmed via current
    upstream fixture as an ordinary tool_uses entry**
    `{"name": "transfer_to_agent", "args": {"agent_name": …}}`.
  - `adk-eval-docs-gdk.md` — adk.dev current: 4 eval run modes (web UI, pytest,
    `adk eval`, new `adk conformance` deterministic replay); 12-criterion table
    (criteria page authoritative; overview list stale); GCP-project-required
    subset (safety_v1, multi_turn_*) — we have ADC; per-case rubrics additive.
  - `repo-claim-verification.md` — **all 13 phase-doc claims CONFIRMED, none
    stale.** Open item 6 leak REPRODUCED live (1 failed, real 403 to
    test-bucket, tests/e2e test_video_review_table). `make lint`: 42 errors,
    30 auto-fixable (ws10 item 4). No tests/integration/conftest.py, no
    test_config.json, no test-live target anywhere. Existing slow/veo tests
    MOCK Veo — no genuinely-live media test exists today. Judge inputs:
    archetypes app/tools/prompt_archetypes.py:16-24, no-text policy
    prompt_builders.py:32-40. ws14 eval candidates verbatim at
    14-model-upgrades/WORK_LOG.md:147-151. reset-db echo says "22 fashion
    products", actual 28. Root conftest: app.config imported line 45 BEFORE
    session env fixture (54-77) — ws15 mechanism confirmed. Worktree .venv
    Python 3.14 + google-adk 2.5.0; app/.env copied from main checkout
    (gitignored).
- Next: working doc draft → owner gate (incl. lint fold-in proposal, agents-cli
  hybrid architecture decision, skills-vendor-on-branch flag).

## 2026-07-23 — checkpoint 2: working doc approved (owner)

Owner gate answers (verbatim):
1. Working doc: "Yes — approved, write the plan" (hybrid pytest+agents-cli
   architecture, 10-stage incremental plan, coverage matrix approved).
2. Lint fold-in (ws10 item 4): "Yes — fold in as stage 0 (Recommended)".
3. agents-cli skills vendor: "Keep on branch (Recommended)" — commit 3fd4879
   stands, ships to client with the PR.
Next: writing-plans → plan.md alongside this doc, then plan-approval gate.

## 2026-07-23 — checkpoint 3: plan approved (owner)

Owner answer (verbatim): "Yes — approved, execute" — plan.md (18 tasks / 10
stages, owner-gate protocol) committed eb86949. Execution via
subagent-driven-development, ultracode workflow loop (implementer → reviewer →
fix cap 2 per task), Tasks 1–5 first (no owner gates); Tasks 6+ pause at each
OWNER GATE per the plan's execution protocol.
Task 1 implemented (commits 9023e93..295fc3e; ruff 42 errors -> 0, make lint green, make test-unit 314 passed/1 skipped, make test-e2e 25 passed/1 skipped, golden prompt tests 4 passed)
Task 1 review: approved (9023e93..41ac6eb)
Task 2 implemented (commits f5c26fc..3aa9c7e; combined tests/unit + tests/e2e 341 passed/2 skipped, was 3 failed/1 skipped before fix; make lint green)
Task 2 review: approved (f5c26fc..4c16ebc)
Task 3 implemented (commits 67da5ee..6921bda; make test = 316 passed/1 skipped (unit) + 25 passed/1 skipped (e2e), no integration output; make lint clean; make test-live invokes pytest tests/integration tests/live — tests/live collects 0 items cleanly, tests/integration pre-existing ModuleNotFoundError: pandas/google-adk[eval] unrelated to this task, out of scope, Task 4+ owns it)
Task 3 review: approved (67da5ee..a65f3ad)
Task 4 implemented (commits 12ebc02..1381958; tests/integration/test_live_env_smoke.py 2 passed; make test 316 passed/1 skipped (unit) + 25 passed/1 skipped (e2e); combined tests/unit+e2e+smoke 343 passed/2 skipped; make lint clean on touched files)
Task 4 review: approved (12ebc02..f3ed7d3)
Task 5 implemented (commits a02141f..cad2c54; tests/integration 7 passed/5 xfailed in 168.54s — evals genuinely run live (was vacuous ~5s), guard+smoke 7 passed; make test 316 passed/1 skipped (unit) + 25 passed/1 skipped (e2e); make lint green; installed google-adk[eval]==2.5.0 extras into worktree .venv — resolves Task 3's carried pandas ModuleNotFoundError)
Task 5 review: approved (a02141f..73d9f1d)

## 2026-07-23 — Tasks 1–5 complete (stage 0–3), all review-approved, 0 fix rounds

- Per-task ledger lines above (mirrored from .superpowers/sdd/progress.md by the
  agents themselves). Highlights: lint 42→0 (UP042 via StrEnum, py311 target);
  item-6 leak reproduced as 3 failures (not 1 — brief's own mechanism paragraph
  was right), combined tests/unit+e2e now 341 passed; tier split landed; live
  smoke proves real project + GCS_BUCKET=None reach the process; eval harness
  live run: 7 passed + 5 xfailed in 168.5s — the five eval sets genuinely
  execute inference + FinalResponseMatchV2 judge scoring now (old vacuous run
  ~5s), xfail-as-authored pending stage-4 repair.
- Carried to Task 16 (docs): worktree needed `pip install 'google-adk[eval]==2.5.0'`
  (pandas chain) — SETUP_INSTRUCTIONS must document the eval extra for test-live;
  eval_harness raises loud ImportError with instructions if absent.
- Task 5 sanctioned deviations (implementer, reviewer-approved): removed
  known-vacuous TestAllEvalSets; factored conftest env bootstrap into
  resolve_live_env()/apply_live_env_to_process() for the recorder CLI.
- skills-lock.json (npx skills integrity hashes) committed alongside the
  vendored skills.
- Next: Tasks 6-10 — record actuals for all five eval sets, then OWNER GATES.

## 2026-07-23 — OWNER GATE 1 (stage 4 calibration): decisions (verbatim)

Presented: calibration/OWNER_REVIEW.md (16 cases, live actuals + proposals;
two reproducible product bugs). Owner answers:
1. Dup-product bug (create-campaign-beverage; settles Task 11 cold-start case
   the same way): "Fix agent now (Recommended)" — amend instructions to
   resolve existing products before creating; pin correct 3-call trajectory
   (list_products → create_campaign product_id=23).
2. Maps misrouting bug (get-map-data): "Fix routing now (Recommended)" —
   Maps-link queries must reach analytics_agent's get_campaign_map_data; pin
   correct 2-call trajectory. Noted: answer text fabricated link-looking text.
3. Pinning policy (other 14 cases): "Yes — minimal refs + proposed bullets
   (Recommended)" — minimal meaningful trajectories (subsequence tolerance),
   OWNER_REVIEW.md's proposed must-contain bullets become the references.
4. review_agent pending-videos verbosity: "Minimal ref, leave agent as-is
   (Recommended)" — drop legacy list_pending_videos from the reference, no
   instruction tightening.

DISCOVERY (bug 2 is new knowledge): Coordinator misroutes Maps-link queries
to campaign_agent; answer text claims Google Maps links that no called tool
produced. Blast radius: app/agent.py routing instructions (fixed this
workstream per decision 2); eval set analytics_agent/get-map-data. Bug 1 was
already flagged by ws14's WORK_LOG (candidate case) — now reproduced live and
being fixed here, which resolves Task 11's open fix-vs-xfail question as FIX.

## 2026-07-23 — checkpoint 4: stage 4 implemented (Tasks 6-10 + owner gate 1 agent fixes)

Post-OWNER-GATE-1 execution (implementer). Base dc289e4.

**Two owner-mandated agent fixes (app/agent.py):**
- **Dup-product fix** (decision 1): commits e69f0b2 (campaign_agent "Creating
  Campaigns" + coordinator Campaign-Agent bullet now require resolving an
  existing product before create_product) + 24754e0 (gave campaign_agent its
  OWN list_products tool — instruction-only was insufficient: the model
  bounced campaign_agent->media_agent->campaign_agent and still created a
  duplicate product id 585 because no list_products call ever fired; giving
  campaign_agent list_products makes the owner-pinned 3-call trajectory real).
  Confirmed live: create-campaign-beverage now runs [transfer(campaign_agent),
  list_products(beverage), create_campaign(product_id=23)], NO create_product,
  all 3 dims 1.0.
- **Maps-routing fix** (decision 2): commits 1f50278 (coordinator Analytics-
  Agent bullet + campaign_agent responsibilities: Google-Maps-link / "on a map"
  queries go to analytics_agent.get_campaign_map_data; campaign_agent's
  get_campaign_locations returns plain addresses only, no Maps links) + 8054c3a
  (analytics instruction nudges get_campaign_map_data() to a no-argument call
  for stable trajectory args — the model was flapping between {} and the three
  explicit include_* default flags; the ADK trajectory evaluator does EXACT
  args equality per pinned call, so an unstable arg set fails tools/trajectory
  intermittently; the nudge stabilized it to {} across repeated runs).
  Confirmed live: get-map-data now routes [transfer(analytics_agent),
  get_campaign_map_data({})], all 3 dims pass.

**Five eval sets repaired** (one commit each): coordinator 696e4ba, campaign
cd6051a, media ee02c87, analytics f0e8a74, review 12fa6aa. Each: pinned the
real transfer_to_agent-wrapped trajectory with minimal-but-meaningful args
(exact-match per OWNER_REVIEW proposals; Option A for create-campaign-beverage
product_id=23 and get-map-data; minimal refs for get-campaign-locations and
list-pending-videos, dropping legacy list_pending_videos); replaced every
empty/stale final_response with a compact factual reference embedding the
owner-approved must-contain bullets (seeds FinalResponseMatchV2). xfail markers
removed per set; the shared _AUTHORED_PRE_TRANSFER marker definition removed
with the last (review) commit. expect_cases set to real counts (4/4/5/4/3).

**Green loop:** full `tests/integration` = **12 passed / 0 failed / 0 xfailed**
in 112.98s (16 eval cases x 3 dims + guard 3 + smoke 2). Two owner-flagged bug
cases both pass all three dimensions. make test (unit+e2e) 341 passed/2
skipped; make lint green on all touched files.

**Deliberate-break (plan Task 6 Step 5):** corrupted coordinator.test.json
list_campaigns -> list_campaignsX; coordinator test FAILED with
`route-to-campaign-agent-list[tools]: score=0.0 < 1.0` and
`route-to-campaign-agent-list[trajectory]: score=0.0 < 1.0`; reverted -> 1
passed. Confirms the tools/trajectory dimensions genuinely gate on tool names.

Calibration nuance worth noting for downstream tasks: exact-arg trajectory
matching + LLM non-determinism means tools with several optional/default args
(e.g. get_campaign_map_data's include_* flags) can flap; the mitigation used
here is an instruction nudge toward a canonical call shape plus pinning that
shape, NOT loosening the eval.

## 2026-07-23 — checkpoint 4b: stage-4 review fix (Important finding)

Review returned one Important finding (all else approved): campaign_agent's
`description=` (app/agent.py:191) still said "location/map features". ADK
injects each sub-agent's description verbatim into the coordinator's
transfer-decision prompt (google/adk/flows/llm_flows/agent_transfer.py), so the
description contradicted the new instruction text and risked reintroducing the
Maps misroute (owner decision 2).

Fix (commit b5be5a7): campaign_agent description now reads "Manages ad
campaigns (create, list, view, update) and store location/address lookup (plain
store addresses only — Google Maps links and maps come from the Analytics
Agent), AND onboards new products into the catalog...". Checked the other three
sub-agent descriptions: analytics_agent (line 425) correctly OWNS the Maps
claim ("provides Google Maps integration with store locations, static maps..."),
media_agent and review_agent carry no map language — no other contradiction.

Verification: make test-unit 316 passed/1 skipped; make lint green. Live
re-run `pytest tests/integration/test_agents.py -k "analytics or campaign"`
(the -k filter also pulls in the coordinator test via its method name):
campaign_agent PASS, analytics_agent PASS; coordinator hit a TRANSIENT Vertex
`400 INVALID_ARGUMENT` on route-to-media-agent-products during inference (the
vacuity guard correctly FAILED rather than passed it — 400 INVALID_ARGUMENT is
not in the infra-marker xfail list), and passed clean on immediate re-run (1
passed in 53s). Not a regression from the description edit (that touched only
campaign_agent; the error was on the media-routing turn).

Stage 4 review: approved (dc289e4..f1b2ac3)
Task 11 implemented (commits 526779e..8717b12; campaign_agent.test.json +create-campaign-cold-start-outerwear case [transfer(campaign_agent), list_products({}), create_campaign(product_id=8)] NO create_product, stable across 6 live runs, all 3 dims pass — OWNER GATE 1's dup-product fix confirmed live for a fresh product; fixed video_tools._variation_params_for_storage to drop model_ethnicity/activity for non-wearable archetypes, 3 new fast unit tests; full tests/integration 12 passed/0 failed in 124s, tests/unit+e2e 344 passed/2 skipped, make lint green)
Task 11 implemented (commits 526779e..98b04c8; fixed review finding — dropped hardcoded live "(Campaign ID 5)" from create-campaign-cold-start-outerwear eval reference [race-condition flakiness risk]; tests/unit/test_video_tools.py::TestVariationParamsStorage 3 passed; tests/integration/test_agents.py::TestCampaignAgent 1 passed (live); tests/unit 319 passed/1 skipped; make lint green)
Task 11 review: approved (526779e..2d47ca3)
Task 12 implemented (commits e411976..4d61789; tests/live/test_media_pipeline.py 2 passed in 187.5s live — wearable [blue-floral-maxi-dress, gen 90s, reference_image_used=false honest] + non-wearable [aurora-cold-brew-330ml, gen 96s, reference_image_used=true, variation renamed beverage-cafe-vibrant, model fields dropped from stored params]; scene images 768x1376 PNG, videos 720x1280@24fps 4.01s ~1.2-2.1MB, no storage.googleapis.com in results; Q14/Q15 evidence in calibration/media-metadata.json; make lint green; unit 319 passed/1 skipped, e2e 25 passed/1 skipped)
Task 12 review: approved (e411976..492c49f)
Task 13 implemented (commits e3006e2..9c0583a; tests/live/test_onboarding_from_scratch.py 1 passed in 32.00s live — non-fashion product [Artisan Coffee Beans] on schema-only empty DB: create_product (pending) -> generate_product_image via real image model (available, product-images/artisan-coffee-beans.png, verified coherent labeled coffee-bag photo) -> create_campaign attach, no storage.googleapis.com anywhere; image registered in generated_media for Task 14's judge; make lint green; unit+e2e 340 passed/2 skipped, golden prompt tests 4 passed)
Task 13 review: approved (e3006e2..9b2a07f)

## 2026-07-23 — controller notes after Tasks 11–13 (all approved)

- Task 11 note: the legacy variation-fields writer fix (video_tools
  _variation_params_for_storage) was executed under OWNER GATE 1 decision 1's
  "fix, don't xfail" precedent (controller dispatch instruction), not a
  separate owner gate — flagged to the owner at the next gate for
  ratification. Cold-start phrasing lesson: "New York, NY" produced unstable
  state args; pinned query uses "Manhattan, New York" (stable across 6 runs).
- Live-flakiness watchlist (for Task 16 docs + Task 18 verification):
  transient Vertex 400 INVALID_ARGUMENT (not in _INFRA_MARKERS — correctly
  FAILS, passes on rerun) seen twice; answer-dimension judge flap seen once
  on get-campaign-locations. Frequency so far ≈1 case per full-suite run,
  always clean on immediate rerun.
- Q14 evidence (Phase 14a): Stage-1 scene images 768x1376 PNG (~1.4MB).
  Q15 evidence (Phase 14b): Veo 3.1 output 720x1280 @ 24fps, 4.01s for a
  requested 4s (6s/8s unmeasured). In calibration/media-metadata.json.
- Generated media on disk for Task 14's judge: generated/ videos (wearable
  blue-floral-maxi-dress 2.1MB; non-wearable aurora-cold-brew 1.2MB),
  product-images/artisan-coffee-beans.png (1408x768).

## 2026-07-23 — checkpoint 5: Task 14 pre-gate (Gemini judge + calibration)

Implementer, pre-OWNER-GATE-2 only (the gate is the controller's). Base
e47c541; code+calibration commit ad5671f.

**judge.py** (`tests/live/judge.py`): gemini-3.6-flash multimodal reviewer
(Vertex, global) via `google.genai`, structured JSON verdicts through
`response_schema` (Pydantic `_Check{verdict,evidence}` per named check).
Public API `judge_image` / `judge_video` / `judge_chart` (+ `judge_media_entry`
dispatch); `JudgeVerdict` = `{check: {verdict, severity, evidence}}`. Severity
is module-owned policy (`_IMAGE/_VIDEO/_CHART_SEVERITY`), NOT model-decided.
Rubric derived from source so judge/generator can't drift: subject rule from
`prompt_archetypes.WEARABLE` (wearable=human model; else product-hero no
humans), no-text policy from `prompt_builders._NO_TEXT_BLOCK`/`_AUDIO_BLOCK`.
Video judged via **direct mp4 bytes** (proven pattern from
`video_tools.analyze_video`), with a 4-evenly-spaced-frames ffmpeg fallback
(`_sample_frames`) if the API refuses on size/format. Honesty bound: pixels
only — videos check burned-in captions per visible frame, audio NOT verified
(rubric text says so).

**test_media_judge.py**: `test_generated_media_obey_rubric` judges every
`generated_media` entry (registry-or-disk resolver `_resolve_media` — works
in-session AND standalone off disk, skip-with-reason if absent), FAILS on any
hard-check fail, `warnings.warn` on warn checks. `test_rpi_chart_obeys_inverted_rubric`
renders one chart via the REAL `metrics_tools.generate_creative_comparison_chart`
(seeded campaign 1, MagicMock ToolContext to capture PNG bytes, tmp_path) and
judges it with the INVERTED rubric: axis/label/value text REQUIRED + bar count
== seeded activated-creative count (3). Marks `[live, slow]`.

**Calibration live run** (once, over EXISTING disk media + fresh chart):
5 media (2 videos, 2 scene images, 1 onboarding product image) + 1 RPI chart,
6 multimodal judge calls in one pass → **ALL hard checks pass, all 3 warn
checks pass, zero failures**. Both videos used direct-mp4 (fallback NOT
exercised). Chart: 3 bars confirmed, axes/labels/value tags legible.
Verdicts + evidence sentences + proposed hard/warn split written to
`calibration/judge-calibration.md`; the rendered chart saved to
`calibration/rpi-chart-campaign1.png` (owner opens both at the gate).

**Proposed severities (NOT owner-pinned — decided at OWNER GATE 2):**
subject_matches_archetype=hard, no_rendered_text=hard, no_captions_any_frame
(video)=hard, setting_mood_plausible=warn; chart axes_and_labels_legible=hard,
correct_creative_count=hard. Open for the owner: keep setting_mood as warn or
promote; confirm chart checks hard; want a product-identity check?

**Limitations flagged:** no negative controls this run (all media is
policy-conformant, so this proves no-false-positive, NOT catch-violations —
a text-injected image / human-in-product-hero would be the negative control,
deferred to owner/Task 16). Ordering nuance: in a full `make test-live` the
judge file sorts before the pipeline file alphabetically, so in-session the
judge falls back to on-disk media from a prior run unless reordered — the
resolver is order-independent by design; flag for Task 14 Step 4 (controller).

**Verify (pre-gate):** make lint green (all touched); make test-unit 319
passed/1 skipped. NOT run: full `make test-live` (Step 4, controller);
regeneration of existing videos/images (expensive, reused on disk).

## 2026-07-23 — OWNER GATE 2 (judge calibration): decisions (verbatim)

Presented: calibration/judge-calibration.md (5 media + chart, all checks pass,
per-check evidence; media paths listed for owner viewing). Owner answers:
1. Severity mapping: "Approve as proposed (Recommended)" — hard:
   subject_matches_archetype, no_rendered_text, no_captions_any_frame, both
   chart checks; warn: setting_mood_plausible. (Resolves phase-doc open
   question 1; Task 16 amends 99-open-questions.)
2. Judge negative controls: "Yes — add now (Recommended)" — corrupted-media
   fixtures the judge must FAIL become part of test-live.
3. Task 11 legacy variation-fields fix: "Ratified (Recommended)".
