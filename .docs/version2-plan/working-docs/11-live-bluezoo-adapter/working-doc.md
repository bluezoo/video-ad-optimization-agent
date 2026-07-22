# Workstream 11a: audience-provider-seam (port)

**Branch:** version_2_live-bluezoo-adapter
**Phase doc:** .docs/version2-plan/11-live-bluezoo-adapter.md — **11a half only** (steps 2, 4, and the synthetic conformer from step 3). 11b (live/cached BlueZoo conformers) stays blocked on open questions 1/2 and is out of scope.
**Owner directives at kickoff:** carried items 1 (`_load_attribution_windows` empty-list `IN ()` guard) and 2 (mock_data/review_tools window-load SQL duplication) are in scope; `APP_MODE` gets wired to provider selection here; items 3 (window-history growth) and 4 (repo-wide lint) stay deferred.

## Research findings

Verified by three parallel readers (donor repo, this repo's seam surface, plan docs), 2026-07-22. Full structured output in the session workflow journal; WORK_LOG.md carries the digest.

**Donor (`/Users/lavi/gwork/ad-campaign-agent`, strictly read-only) — everything the phase doc claims exists, exists:**
- `AudienceProvider` ABC (`services/audience_provider/provider.py:42`) with keyword-only typed reads returning Pydantic models, an SQL escape hatch (`list_metric_tables`/`describe_metric_table`/`run_metric_query`), and an attribution write surface.
- Selection factory (`services/audience_provider/__init__.py:47-183`): env var `AUDIENCE_PROVIDER`, entry-points lookup falling back to a `_BUILTIN_PROVIDERS` dict, thread-safe singleton, `register_provider_for_tests()`/`reset_audience_provider()` test seam, and the fail-loud missing-env `RuntimeError` (`_autoinstantiate`, lines 124-135).
- `MockInMemoryProvider` (pandas frames + DuckDB escape hatch) and `MockBigQueryProvider`; sqlglot `QueryGuard` (SELECT-only, allowlist, LIMIT clamp).
- All three phase-doc caveats confirmed at exact lines: `0.05` in **three** places (two class attrs + a raw SQL literal at `mock_bigquery.py:500`); string-replace table qualification (`_qualify_tables`, `mock_bigquery.py:219-227`); viz tool regressed to a stub (donor `app/tools/metrics_tools.py:319-363`) — whose own error message admits the root cause: **the donor interface has no daily-grain read**, only whole-window aggregates.
- **No shared contract-test suite in the donor** — per-provider test files only. The phase doc's "provider conformance test" pattern is new infrastructure we build, not something to lift.
- Donor traps we will deliberately not copy: the fail-loud check requires `GCS_BUCKET`, which the BQ provider never uses (a false coupling to an unrelated storage service); the default provider is `mock_bigquery` (wrong default for a zero-setup demo mode); `_autoinstantiate` reaches into `campaign_service` for demo seeding (cross-module reach-in violating our layering); the BQ provider instantiates the in-memory provider internally to reuse its dwell aggregation.

**This repo — the seam is 100% net-new, and the phase doc's premises hold:**
- `APP_MODE` (`app/config.py:17-37`): `AppMode` StrEnum, default `DEMO`, `ValueError` on garbage, **zero consumers** (grep-confirmed; `scripts/deploy_ae_inline.py:310` only forwards the env var). Pinned by `tests/unit/test_config.py:67-103`.
- `app/demo_data/seed.py` is import-light (stdlib + numpy) and its docstring promises verbatim: "Phase 11a moves this file behind the AudienceProvider seam as-is."
- The join consumes exactly one frame: `derive_rows_from_windows` calls `generate_frames()` internally and reads only `frames["screen_visits"]` (`app/demo_data/attribution.py:159`) — inner counts → impressions, outer-out → circulation; dwell is a separate seeded RNG scalar; the other four frames are generated and discarded (except the `video_attribution` frame, used only at seed time by `seed_video_attribution` paths).
- `BlueZooVisitInterval` (`app/models/attribution.py:43-61`, `extra="forbid"`, includes optional `ad_campaign_id`) is currently **decorative**: defined, exported, schema-tested, never constructed in any production path. `screen_visits` frame rows validate against it directly.
- Carried item 1 confirmed: `review_tools._load_attribution_windows` (`app/tools/review_tools.py:117-137`) builds `IN ()` for an empty `video_ids` list — unreachable today (every call site passes `[video_id]`).
- Carried item 2 confirmed: `app/database/mock_data.py:362-366` re-implements the same 4-line window-load SQL, with the layering rule ("mock_data must not import app.tools") existing only as an inline comment.
- Consumer insulation: **all** read-side tools (`get_campaign_metrics`, `get_campaign_insights`, `compare_campaigns`, `compare_creatives_within_campaign` + chart) read the materialized `video_metrics` table, never the generator. Daily grain nuance: only the first two GROUP BY `metric_date`; the creatives chart is per-video all-time. So the daily-grain requirement is satisfied by keeping the per-(video, day) `video_metrics` materialization exactly as is — the seam must sit *below* it.
- `DEMO_RPI = 0.05` is already the single canonical constant (`app/demo_data/constants.py:13`) — this donor caveat was pre-fixed in earlier workstreams. (Minor: that file's docstring says the donor duplicated it in *two* places; the audit found three — one-line docstring fix folded in here.)

**Plan docs:** Q1/Q2 remain open → 11b exclusion stands; Q11/Q12/Q17 don't touch 11a. Phase 6's amendment pins the fail-closed guard contract: a clear, specific error at the provider-selection factory when `connected` is requested but no adapter/credentials exist — not `NotImplementedError`, not a silent fallback to demo. All five BlueZoo-mapping port corrections are verified implemented. 00-overview rates 11a **Medium**.

**DISCOVERY (logged in WORK_LOG, doc 11 amended):** Phase 10 never defined an "AudienceDataSource" interface — doc 11's line-5 phrase "renamed/merged with Phase 10's AudienceDataSource DTO contract" overstates it. Phase 10 supplied DTOs only; the interface name is doc 11's own coinage. Correct framing: one new interface whose reads return Phase 10's existing DTO shape.

## Implementation approach

**How might we put demo mode behind the same interface live mode will use?** Three candidates were stress-tested:

**Option A (chosen) — lean BlueZoo-shaped seam at the visit-interval boundary.** The interface exposes what BlueZoo actually is to this app: a read-only source of per-(screen, 15-min slot) visit intervals. The donor's *mechanics* (factory, registry dict, singleton, test seam, fail-loud guard) are ported; the donor's *method surface* is not — it serves tools this repo doesn't have, and its whole-window aggregates are exactly what regressed the donor's chart tool.

**Option B (rejected) — port the donor ABC surface wholesale** (typed engagement/dwell/UV/flow reads + SQL escape hatch + QueryGuard). Rejected: none of this repo's tools would call any of those methods (they read `video_metrics`); it imports the donor's daily-grain regression instead of avoiding it; the escape hatch has no consumer here, so QueryGuard would guard nothing (the phase doc itself makes QueryGuard conditional on porting that surface); pure dead abstraction — fails the plan's own don't-overcomplicate philosophy.

**Option C (rejected) — function-level swap without an interface** (a module-level `get_visit_intervals()` that branches on APP_MODE internally). Rejected: no structured place for the fail-closed guard, the test-registration seam, or 11b's conformer to slot into; no interface for a contract-test suite to assert against; contradicts the phase doc's explicit mandate to port the interface + selection factory.

### Shape of the chosen approach

New package `app/audience/` (imports `app/models` + `app/demo_data/seed.py` only — no cycles: nothing in `app/demo_data` imports `app/audience`):

- **`app/audience/datasource.py`** — `AudienceDataSource` ABC (doc 11's name; per the DISCOVERY, it's the donor's `AudienceProvider` renamed, returning Phase 10's DTO):
  - `get_visit_intervals(*, screen_ids: list[int], date_from: date, date_to: date) -> list[BlueZooVisitInterval]` — keyword-only like the donor; returns the DTO, not pre-aggregated ints (phase doc step 2, verbatim requirement). This signature is exactly what 11b's live conformer must answer from `sensor_visits` (screens + window in, intervals out), so the seam is honest: no synthetic-only parameters (no `ad_campaign_id`, no seed config) leak into it.
  - Read-only. The donor ABC's attribution *write* surface is deliberately not ported: attribution windows are this app's own domain (CMS/ad-play side, stored in SQLite by the ws10 bridge), not audience data BlueZoo serves.
- **`app/audience/synthetic.py`** — `SyntheticAudienceDataSource(AudienceDataSource)`: wraps `seed.py` as-is (fulfilling its docstring). Derives the campaign context internally from `screen_id // 100` (the ws10 convention: `screen_id = ad_campaign_id * 100 + k`), builds the same `SeedConfig` the join builds today, calls `generate_frames()`, filters `screen_visits` to the requested screens/window, and returns rows as `BlueZooVisitInterval` instances — making the DTO load-bearing for the first time. Determinism is inherited wholesale from seed.py.
- **`app/audience/__init__.py`** — the factory, ported from the donor's mechanics with the traps fixed:
  - `get_audience_datasource() -> AudienceDataSource`: resolves from `config.APP_MODE` (not a new env var — APP_MODE is deliberately the only user-facing mode knob, per Phase 6). `demo` → `SyntheticAudienceDataSource`. `connected` → **the Phase-6 fail-closed guard, now real**: raise a clear, specific `RuntimeError` stating that `APP_MODE=connected` requires the live BlueZoo adapter (Phase 11b, not yet built), what credentials it will need, and how to get back to a working state (`APP_MODE=demo`). No silent fallback, no `NotImplementedError`, no `GCS_BUCKET`-style false coupling — the guard checks only what this seam actually needs.
  - Builtin dict registry (`_BUILTIN_SOURCES: dict[AppMode, ...]`) — the donor's dict pattern, keyed by the mode enum; entry-points packaging skipped per the phase doc. 11b later replaces the `connected` entry's guard with the real conformer.
  - Thread-safe singleton + `register_datasource_for_tests()` / `reset_audience_datasource()` — the donor's test seam, ported as-is.
- **`app/demo_data/attribution.py` refactor** — `derive_rows_from_windows` stops calling `generate_frames()` directly; it obtains intervals via the seam (`source.get_visit_intervals(...)`, source defaulting to the factory) and indexes them by `(screen_id, timestamp)` exactly as today. This is the one production call path through the interface, which is what makes the seam real rather than ceremonial. Byte-identical `video_metrics` output is the non-negotiable refactor invariant (existing determinism tests pin it).
- **Carried items 1+2** — new shared helper `app/demo_data/windows.py`: `load_attribution_windows(cursor, video_ids) -> list[dict]` with the empty-list guard (`return []` before building SQL — item 1), used by both `review_tools.py` and `mock_data.py` (item 2; legal layering — both already import from `app/demo_data`, and `app/demo_data` imports neither).
- **Docstring touch-ups:** seed.py's "Phase 11a moves this file behind the AudienceProvider seam as-is" line updated to reflect it happened; `constants.py` docstring two→three places.

**Explicitly ported from the donor:** factory/registry/singleton/test-seam mechanics, the fail-loud error style (with its message rewritten for APP_MODE and without the false env couplings).
**Explicitly not ported:** the wide typed method surface, QueryGuard + SQL escape hatch (no consumer here; phase doc makes it optional for 11a), entry-points packaging, `MockBigQueryProvider`, the attribution write surface, the campaign-service reach-in.

## Test plan

- **Unit (new):**
  - Contract-test suite (`tests/unit/test_audience_datasource.py`): a reusable battery asserting interface conformance — returns `BlueZooVisitInterval` instances, respects screen/window filters, deterministic across calls, timestamps at 15-min grain, inner/outer fields non-negative. Runs against `SyntheticAudienceDataSource` now; written so 11b's conformers plug into the same battery (the phase doc's validation pattern).
  - Factory tests: `demo` → synthetic (singleton, same instance twice); `connected` → the specific fail-closed error (message names Phase 11b + APP_MODE=demo escape hatch); test-registration override + reset; no fallback-to-demo on `connected`.
  - `load_attribution_windows`: empty list → `[]` (no SQL executed), non-empty parity with the previous inline SQL in both callers.
- **Unit (existing, unchanged — the refactor invariant):** `test_demo_attribution.py`, `test_review_tools.py` (TestAttributionBridge incl. reactivation), `test_mock_data_attribution.py`, `test_metrics_tools.py`, `test_config.py` must pass **without modification** — they pin RPI band/keying, absoluteness, inner-only impressions, overlap dedup, and derive/DB parity. A before/after `video_metrics` byte-comparison on the seeded demo DB is the acceptance check that the seam refactor changed nothing observable.
- **Demo scenarios (`verifying-with-demo-scenarios`):** re-run `docs/demo-scenarios/fashion.md` **F3** (campaign metrics/RPI) and **F4** (creatives chart) — the two scenarios reading through the refactored derive path — expecting identical behavior to ws10's passes. Plus a **fail-closed smoke**: start the server with `APP_MODE=connected` and verify startup/first-tool-use surfaces the specific guard error (scripted check, not a browser scenario).
- **demo_guide.md:** add a Part covering the new APP_MODE behavior (demo default unchanged; `connected` now fails loudly with the guard message) so the owner can verify the knob by hand; prune nothing (no journey is invalidated — demo behavior is byte-identical by design).

## Out of scope

- **All of 11b:** `LiveBlueZooAudienceDataSource`, `CachedBlueZooAudienceDataSource`, REST-vs-BigQuery transport (Q2), secret handling / AccessKey, screen↔sensor mapping (Q11), sandbox account (Q12), sub-15-min window fallbacks (Q17), retry/timeout/pagination policy (phase doc step 7).
- QueryGuard and any SQL escape-hatch surface; entry-points packaging; the donor's BQ provider.
- Typed dwell/UV/flow read methods (no consumer in this repo; 11b+ can extend the ABC when one exists).
- Carried items 3 (closed-window history growth) and 4 (repo-wide lint cleanup) — deferred per owner directive.
- `seed.py` algorithm changes (wrapped as-is; only its seam-promise docstring line updates), `README.md`, `DEMO_GUIDE.md` (root), `video_metrics` schema, and all read-side tool behavior.
