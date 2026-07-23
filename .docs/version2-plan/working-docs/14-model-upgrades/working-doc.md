# Workstream 14 (combined): model upgrades — 14a + 14b + agent default

**Branch:** version_2_model-upgrades (one branch/PR; STATUS rows 14a and 14b both track it)
**Phase docs:** `.docs/version2-plan/14a-image-model-upgrade-nano-banana.md`, `.docs/version2-plan/14b-video-model-upgrade-omni-flash.md`, plus the agent-model default change pulled forward from `.docs/version2-plan/16-live-api-testing.md` step 3 (owner directive, 2026-07-22).

**Structure (owner directive):** three sequential tasks — Task A (14a) → Task B (14b) → Task C (agent default) — each independently verified and committed.

## Research findings (kickoff re-verification, 2026-07-22)

### 14a — image model

- Drop-in swap already pre-verified (ws01 amendment in the phase doc): `IMAGE_GENERATION_MODEL=gemini-3.1-flash-lite-image` produced an on-brief image through the unmodified call path. **Remaining 14a work is only the documented side-by-side comparison** (and a default decision from it).
- `IMAGE_GENERATION` default `gemini-3-pro-image` at `app/config.py:70` (override `IMAGE_GENERATION_MODEL`). `generate_scene_image()` drifted from the doc's citations: def now at `app/tools/video_tools.py:196` (ws09 added an `archetype` param), API call at `:248-254`.
- **STALE in phase doc — the knob is shared by FOUR runtime call sites, not just Stage 1:** `video_tools.py:249` (Stage-1 scene image, media agent), `metrics_tools.py:1208` (analytics infographics), `maps_tools.py:1316` (revenue heatmap images), `onboarding_tools.py:215` (`generate_product_image`, campaign agent). The chart/map users are dense-text legibility use cases where Nano Banana 2 Lite's 1K-output cap could hurt most, and they use a different call config (`response_modalities=["IMAGE"]` + 16:9). Any default-change recommendation must weigh all four.
- Phase 8's retail core set exists (6 non-wearable products across 5 verticals, `app/database/retail_products_data.py:14-97`), **but their image PNGs don't exist on disk** — the non-fashion half of the comparison starts from generation with no reference image (the reference-image preamble branch at `video_tools.py:233-246` is skipped), which is a real difference in what's being compared vs the fashion half.
- Existing harness: `scripts/smoke_media_models.py` already does swap-and-smoke. Only one test pins the default: `tests/unit/test_config.py:24`.

### 14b — video model

- The three duplicated Veo polling loops are confirmed (lines drifted): `animate_scene_with_veo` loop at `video_tools.py:325-332`, `generate_video_from_product` at `:619-624`, `generate_video_ad` at `:1003-1019`. All poll `client.operations.get()` with blocking `time.sleep()` inside `async def`, max_wait 600s / interval 20s. **Loop 3's timeout semantics differ materially** — it marks the DB row `failed` and returns an error dict instead of raising — so one shared helper needs a caller-chosen raise-vs-return design, and its tests must cover both behaviors.
- The post-loop result-bytes extraction (Vertex `video_bytes` vs Developer-API `files.download` + tempfile) is **also triplicated** (`:337-359`, `:626-642`, `:1026-1071`) — natural second half of the same consolidation, feeding the `GeneratedVideo` contract.
- Persistence lives outside the loops in all three call sites (ws15 storage seam), so a poll+extract helper can be factored without touching save paths. Pre-existing inconsistency noted, NOT fixed here: `generate_video_ad` uses `storage.save_video` only in GCS mode and raw `open()` into `GENERATED_DIR` in local mode (`:1074-1082`), unlike `generate_video_from_product` which always uses the seam.
- No revision/regeneration tool exists on the Review Agent (tools at `app/agent.py:507-520`) — phase-doc claim holds.
- SDK: requirements floor `google-genai>=1.55.0` (`app/requirements.txt:26`); this worktree's fresh `.venv` installed **2.14.0**, `client.interactions` surface present (create/get/cancel/delete). ws01's probe (2.11.0) found `gemini-omni-flash-preview` 404s on `generate_videos` and raw-dict `interactions.create` bodies fail — the prototype must use the SDK's typed request path, and `VIDEO_GEN_MODEL` alone cannot select Omni (a separate backend toggle is genuinely needed).
- Test coverage today: **zero** tests on any of the three polling loops; `generate_video_ad` has zero test references at all.

### Agent default (pulled forward from Phase 16 step 3)

- `MODEL = os.environ.get("AGENT_MODEL", "gemini-3.5-flash")` at `app/config.py:64`; consumed by **all five agents** (`app/agent.py:178, 284, 404, 503, 597`) and by `analyze_video()` (`video_tools.py:171` — so the flip also changes the video-analysis model; its docstring at `:99` claims a nonexistent `VIDEO_ANALYSis_MODEL` config, pre-existing drift).
- **Live-probed this kickoff:** `gemini-3.6-flash` responds on Vertex with `GOOGLE_CLOUD_LOCATION=global` (SDK 2.12.1/2.14.0). **GA confirmed** (Google model page: launch stage GA, released 2026-07-21) — so CLAUDE.md:74's "all default to GA IDs" language and the global-location gotcha both survive unchanged.
- Exact edits required: `app/config.py:64`, `tests/unit/test_config.py:23`, `SETUP_INSTRUCTIONS.md:100` (hardcodes the default trio). Optional comment-only cleanups: `scripts/deploy.sh:40`, `scripts/deploy_ae.sh:246`, `scripts/deploy_ae_inline.py:19` (already stale).
- **Golden prompt files are structurally safe:** `tests/unit/data/golden_scene_prompt_product1_asian.txt` + `golden_creative_prompt_product1_asian.txt` pin `prompt_builders.py` output byte-for-byte (`test_product_adapter.py::TestGoldenPrompts`) and contain zero model IDs. This workstream does not touch `prompt_builders.py`, so byte-identity holds by construction; the tests stay green as proof.

### Verification surfaces

- `docs/demo-scenarios/fashion.md` **F1 is self-described as "the release gate for any model-config change"** — inherited as this workstream's primary regression scenario. F5.2 covers non-fashion video (no reference image, `reference_image_used: false`); `from-scratch-onboarding.md` Scene 2.2 covers `generate_product_image`.
- DEMO_GUIDE.md journeys: none invalidated by the MODEL flip; Journey 15.1 (real image-model call) is the image-path regression; **no journey exercises video generation today** — if the omni_flash backend ships, a new journey is required per the ws11a rule.

## Implementation approach

### Task A — 14a: side-by-side comparison, evaluation-first (no default change unless the data says so)

Run the documented comparison the phase doc requires, across **both catalogs and all four consumer shapes**:

1. Fashion (with reference image) and retail-core (no reference) products through Stage-1 `generate_scene_image` semantics, under `gemini-3-pro-image` vs `gemini-3.1-flash-lite-image` (via the existing `IMAGE_GENERATION_MODEL` env override + `scripts/smoke_media_models.py`-style harness runs — no app code changes).
2. At least one chart/infographic-shaped call (`response_modalities=["IMAGE"]`, 16:9) per model — the 1K-cap risk case.
3. Record per-image: file size, decoded resolution, subjective quality notes, latency → comparison doc in this working-docs folder + **Q14 evidence (resolutions) in WORK_LOG**.
4. Decision: default stays `gemini-3-pro-image` unless the comparison clearly favors switching; any switch (or knob-split for charts/maps) is presented to the owner with the evidence, not silently applied. No `ImageGenerator` abstraction (phase doc's own correction — same call surface).

*Rejected:* building a backend abstraction now (phase doc explicitly rejected it; still just two model IDs through one call shape); switching the default on cost alone (4-consumer blast radius, chart legibility risk).

### Task B — 14b: Veo polling consolidation (unconditional) + prototype-gated Omni Flash

- **B1 (unconditional bug fix):** one shared async helper for the Veo poll loop + result-bytes extraction — `asyncio.sleep` instead of blocking `time.sleep`, parameterized timeout behavior (raise for call sites 1-2; structured-return for `generate_video_ad`, whose DB-update stays at its call site). All three call sites converted; persistence/save paths byte-for-byte untouched (including `generate_video_ad`'s local-mode seam bypass — noted, not fixed). New unit tests: success, timeout(raise), timeout(return), failure — coverage where today there is none.
- **B2 (prototype, documented):** small real Interactions API prototype per phase-doc step 3 — SDK **typed** request path (ws01 proved raw dicts fail), `image_to_video` for one product, record request/response shape, working SDK version, and what `previous_interaction_id` actually needs for a meaningful edit. Findings written into this working-docs folder before any schema/tool code.
- **B3 (conditional on B2 proving the mechanics):** `VIDEO_MODEL_BACKEND` config toggle (`veo` default / `omni_flash` experimental opt-in), Omni path normalized into a shared `GeneratedVideo` result contract, the genuinely-new Review Agent revision tool with interaction-ID/lineage storage, SDK floor pinned per prototype, new DEMO_GUIDE journey. **If B2 shows the API immature/unusable, we stop at documented findings**: amend the 14b phase doc + `99-open-questions.md` #15 with the evidence and the wait-for-GA recommendation — a negative evaluation result is a valid phase outcome per the doc's own framing ("evaluate, not adopt"; Veo stays default either way).

*Rejected:* skipping consolidation until Omni decides (B1 is a real bug fix on its own merits — phase doc says do it regardless); one shared polling primitive across both backends (wrong abstraction — operations vs interactions are different API objects; only the *result contract* is shared).

### Task C — agent default → `gemini-3.6-flash`

- `app/config.py:64` default flip (env override unchanged), `tests/unit/test_config.py:23`, `SETUP_INSTRUCTIONS.md:100`, stale deploy-script comments; fix the `analyze_video` docstring drift in passing (same file, one line).
- Amend `16-live-api-testing.md` step 3 with a provenance note moving the item into this workstream (Phase 16 keeps its own re-verify step as a no-op check).
- GA + global-location already confirmed (probe + model page), so CLAUDE.md:74 needs no change — verified, not assumed.

## Test plan

- `make test-unit` + `make test-e2e` green after **each** task (PostToolUse hook enforces unit on every app edit). `TestGoldenPrompts` byte-identity stays green throughout — the golden constraint's proof.
- **Task A:** the comparison itself is the verification (live generations both models, both catalogs, chart shape); no app-code change expected. Q14 evidence → WORK_LOG.
- **Task B:** B1's new polling-helper unit tests (success/timeout×2 semantics/failure); demo scenario **F1** (fashion.md — release gate: full Stage-1 + Veo live run) via `demo-scenario-verifier`; if B3 ships: one real `VIDEO_MODEL_BACKEND=omni_flash` end-to-end video + revision-tool run, new DEMO_GUIDE journey, **F5.2** for the no-reference path. Q15 evidence (video-output notes) → WORK_LOG.
- **Task C:** suites + **F1 re-run on the new agent default** (routing + generation through `gemini-3.6-flash`), plus from-scratch Scene 2.1/2.2 (routing to campaign agent + real image gen) as the cross-agent routing check.
- Storage mode for all live verification: local-first (`GCS_BUCKET=` empty export beats `app/.env`, per ws15's verifier convention) — no `storage.googleapis.com` URLs expected anywhere.

## Out of scope

- **Changing the default video backend** — Veo 3.1 (`veo-3.1-generate-001`) stays default regardless of B2/B3 outcome (phase-doc mandate).
- **`prompt_builders.py` and the golden prompt files** — untouched, byte-identical.
- **Phase 16's test-tier work** (live tier, eval-set repair, vacuity guard, GCS state leak) — only the model-default item is pulled forward.
- **Fixing `generate_video_ad`'s local-mode storage-seam bypass** — pre-existing inconsistency, logged for a future cleanup, preserved as-is by B1.
- **Splitting the IMAGE_GENERATION knob** (e.g., separate chart-image model) — only if Task A's data demands it, and then as an owner decision, not a silent change.
- `README.md` (client-facing, untouched as always).
