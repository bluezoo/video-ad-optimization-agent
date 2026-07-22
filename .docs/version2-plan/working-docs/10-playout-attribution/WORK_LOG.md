# Workstream 10 — playout-attribution: WORK_LOG

Append-only durable history (see tracking-workstream-progress).

## 2026-07-22 — checkpoint 1: kickoff — worktree created
Branch version_2_playout-attribution off version_2 @ 759d0c8 (post-ws09 merge 20d7347).
Phase doc: .docs/version2-plan/10-playout-attribution.md. Dependencies 4/5/8 all merged
per STATUS. Owner kickoff notes to verify in research: (a) doc's "Current state" predates
ws05 — real current state is app/demo_data/derive.py, whose header declares this phase
replaces it with the ad-play join; seed.py untouched; (b) ws07 per-creative RPI factor in
derive.py powers demo scenario F4 — the join-derived world must preserve per-creative RPI
differentiation; (c) honor replan amendments: ad_campaign_id (never bare campaign_id),
BlueZooVisitInterval scoped to sensor_visits fields only, no sub-15-min live-window
assumptions; (d) demo_guide.md refresh required before PR (metric values change).
(Research findings appended when kickoff research completes.)

## 2026-07-22 — kickoff research done (amends checkpoint 1)

Ultracode research workflow `wf_5d1c437a-644`: three parallel readers (demo-data layer, DB/schema/donor bridge, consumers/tests). All four owner kickoff notes verified:

- **(a) HOLDS:** phase doc "Current state" is pre-ws05 stale — `_generate_mock_video_metrics()` gone; real mechanism is `app/demo_data/seed.py` → `derive.py` → `video_metrics`, with `derive.py:1-4`'s header explicitly declaring Phase 10 replaces it with the ad-play join. seed.py needs zero changes.
- **(b) HOLDS:** per-creative RPI = `derive.py:61-70 video_rpi()`, DEMO_RPI × seeded factor [0.6,1.4] → band [0.03,0.07], keyed per (ad_campaign_id, video_id), day-independent. F4 + Journeys B4/B5 pin "not all identical" + "one stable constant per creative" — the join world must preserve this keying.
- **(c) HOLDS:** replan amendments at doc top are current (ad_campaign_id naming, BlueZooVisitInterval scoped to sensor_visits fields, no sub-15-min windows). seed.py grain is 15-min; `campaign_uv_daily` is daily with no screen key.
- **(d) HOLDS:** `.docs/version2-plan/demo_guide.md` journeys B4/B5 are invariant-based (band, arithmetic) but B-journey narrative + F3/F4 walkthrough values will shift — refresh required pre-PR.

## 2026-07-22 — DISCOVERY: seed.py already has the attribution frame and multi-screen support

Assumed (10-playout-attribution.md "Current state"): no screen entity, no ad-play concept anywhere; everything to build from scratch.
Actual: `seed.py:239-254` already emits a `video_attribution` frame — (video_id, ad_campaign_id, screen_id, active_from, active_to), exactly the donor bridge's window shape — returned by `generate_frames()` (:265) and consumed by NOTHING except the shape test (`test_demo_seed.py:40`). And `SeedConfig.screen_ids: list[int]` (:70) is genuine multi-screen support: every frame loops screens; only `derive.py:_campaign_seed_config()` (:21-38) collapses to the 1:1 campaign-as-screen proxy (`screen_ids=[ad_campaign_id]`), which its own docstring says Phase 10 replaces. `BLUEZOO_MAPPING.md` pre-reserves the `video_attribution` frame name for Phase 10.
Blast radius: phase doc "Current state" (amended with provenance this branch); shrinks this workstream's build surface — the bridge builds on the dormant frame, not from scratch.

## 2026-07-22 — DISCOVERY: dwell/circulation have no join story in the phase doc

Assumed: phase doc steps 4-6 cover deriving video_metrics from the join.
Actual: they cover impressions (visits) and revenue (product lookup) only. `dwell_time_seconds` (`derive.py:99`, seeded RNG) and `circulation` (:106-107, outgoing_outer_count × video_fraction) are two of the six columns every reader tool aggregates, and the doc is silent on them. `docs/METRICS.md:45` already defers dwell semantics to Phase 11.
Blast radius: this workstream's design (keep both synthetically derived, attached to the join's play windows; real semantics Phase 11) — recorded in phase-doc amendment + working doc.

## 2026-07-22 — DISCOVERY: BLUEZOO_MAPPING.md still says "flat 0.05" RPI

Assumed: docs current as of ws07's per-creative RPI band.
Actual: one stale provenance line claims flat DEMO_RPI 0.05; reality is per-creative band [0.03,0.07] since ws07.
Blast radius: one-line doc fix, bundled into this workstream (it's editing adjacent lines anyway).

Other load-bearing findings for the working doc: two derive call sites (`review_tools.py:35,117` activation-time; `mock_data.py:28,343` bulk seed-time with NO activation moment — needs synthetic windows, which the dormant seed frame already provides); all 8 video_metrics readers issue raw SQL against the existing table shape → keeping video_metrics as the derived aggregation means zero consumer changes; `test_demo_derive.py` imports derive internals by name → will be rewritten; `test_metrics_tools.py` raw-INSERTs its fixtures → insulated. Donor bridge (read-only /Users/lavi/gwork/ad-campaign-agent): `write_video_attribution`/`close_video_attribution` (provider.py:135-152), 5-col window table, open row = active_to IS NULL, close = earliest open row + SILENT no-op on miss (we will not inherit the silent no-op); port renames store_id→screen_id, campaign_id→ad_campaign_id; do NOT port donor's adjacent query math (inner+outer double-count bug, fixed here in ws05 and pinned by test_demo_derive.py:29-43).

## 2026-07-22 — checkpoint 2: working doc approved

Owner approved the six-dimension restatement as-is ("Yes — approved, write the plan"): attribution windows table + deterministic ad-play join, derive.py rewritten in place as signature-stable facade, screens as in-code deterministic roster (no DB table), ad-plays computed not stored, per-creative RPI keying preserved, dwell/circulation stay synthetic. Next: writing-plans.

## 2026-07-22 — checkpoint 3: plan approved

Owner approved the 8-task implementation plan (plan.md, commit 3eaf5e4): DTOs → video_attribution table → screens/schedule → join+facade → HITL bridge → bulk seed windows → docs/F6/demo_guide → gates. Execution via subagent-driven-development.

## 2026-07-22 — checkpoint 4: all plan tasks complete (mirrors .superpowers/sdd/progress.md)

Implementation via ultracode workflow wf_c4a0486e-109 (14 agents, 7 implement+review pairs, zero fix rounds needed — every task spec-compliant and quality-approved on round 1):

- Task 1 complete (f2661fd..af73b8c) — DTOs; BlueZooVisitInterval validates seed frames verbatim, extra="forbid".
- Task 2 complete (..351eac1) — video_attribution table + index + reset drop; stale local campaigns.db cleared.
- Task 3 complete (..eebad9f) — screens_for_campaign (2-3 screens, ids != campaign id), slot_budget, expand_ad_plays; absoluteness pinned.
- Task 4 complete (..ddf1aed) — derive_rows_from_windows join; derive.py rewritten as signature-stable facade; test_demo_derive.py replaced by test_demo_attribution.py (21 tests).
- Task 5 complete (..e68b496) — dual-write bridge; metrics derive through stored windows (load-bearing, proven by test); close-on-miss warns.
- Task 6 complete (..b53071e) — bulk seed path opens windows; scoped isolation fix to task-2's roundtrip test (flagged, reviewer-approved).
- Task 7 complete (..734c66f) — METRICS.md derivation notes, BLUEZOO_MAPPING.md fixes, fashion.md scene F6, demo_guide.md refreshed. NOTE: brief's METRICS.md find-and-replace target text never existed there (formulas lived in BLUEZOO_MAPPING.md only) — implementer added equivalent "Derivation (demo mode)" content instead; reviewer verified against base.
- Task 8 gates (inline): make test-unit 241 passed / make test-e2e 25 passed; tests/unit/test_metrics_tools.py provably untouched (empty diff vs 759d0c8) = consumers-insulated proof; lint delta -1 vs base (6 pre-existing legacy typing errors remain in review_tools.py, were 7); fresh-DB smoke: 26 windows, 10 distinct screens, 300 metric rows.
- Housekeeping: .superpowers/ scratch untracked + gitignored (ws09 had accidentally committed its reports).

Carried minors for final whole-branch review: db.py init docstring table list omits video_attribution; _load_attribution_windows IN() invalid on empty list (no current call site); reactivation opens a fresh window overlapping the video's closed history; mock_data duplicates the 4-line window load (plan-mandated).

## 2026-07-22 — demo scenario verification: F3 PASS (2/2)

verifier-f3 against this worktree's make dev (:8501). F3.1: get_video_details → 30 days tracked; generate_additional_metrics(days=3) → success; re-check → 33 days (exact 30→+3→33, deterministic). F3.2: compare_creatives_within_campaign → three creatives with DISTINCT RPIs (0.0605/0.0595/0.0589), all in [0.03,0.07], each revenue/impressions rounding exactly to its reported RPI; winner = max-RPI creative. Evidence: scratch/verify-f3/ (session events JSON, tool-call extract, server log). Screenshot writes blocked by chrome-devtools sandbox roots (pinned to another worktree) — claims verified against raw session JSON instead. Side effect: demo anchor advanced +3 days (33-day state is the expected baseline for F4/F6 runs).
