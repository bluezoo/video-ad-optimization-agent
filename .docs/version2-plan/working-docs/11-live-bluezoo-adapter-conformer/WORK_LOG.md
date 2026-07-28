# WORK_LOG — 11b live-bluezoo-adapter (conformer)

Phase 11b, doc `11-live-bluezoo-adapter.md`. Branch `version_2_live-bluezoo-adapter-conformer` off `version_2` (23b0dfe).

## 2026-07-27 — checkpoint 1: kickoff — worktree created
Worktree `.claude/worktrees/version_2_live-bluezoo-adapter-conformer`, base verified == version_2. Research pending (this entry amended when Step 2 completes).

Owner directives at kickoff (binding):
- Honour the three pre-kickoff scoping decisions at the foot of 11-*.md — do NOT reopen: (1) REST-first behind the 11a seam (OUR assumption — surface in working doc, get explicit yes); (2) ONE class implementing ONE method, no registry/plugin framework/second abstraction — growing layers = stop and re-scope; (3) CachedBlueZooAudienceDataSource OPTIONAL, designated trim — if dropped, say so and amend Exit criteria.
- Rule R (WHERE valid, exclusion logged) is a recommendation NOT confirmed by BlueZoo — explicit, logged, CONFIGURABLE policy, never baked in.
- Read-only against BlueZoo, no writes ever. MO_92 = real customer data: redact identifiers, never commit a key, sweep branch pre-PR.
- This workstream CHANGES agent-visible behavior — demo-scenario verification + DEMO_GUIDE.md journeys are MANDATORY before PR (unlike the two research predecessors; do not cite their skip precedent).
- make test stays network-free (350 tests / ~32s protected); live conformer tests go in the live tier (make test-live) so test runs never bill customer quota.
- Credentials already in app/.env (Morpheus/MO_92).

## 2026-07-27 — checkpoint 1 amendment: research done
Seam verified as scoping amendment describes: app/audience = 143 lines/3 files; datasource.py 27 lines, ONE abstract method get_visit_intervals(screen_ids, date_from, date_to) -> list[BlueZooVisitInterval]; factory has _BUILTIN_SOURCES dict with the AppMode.CONNECTED slot explicitly reserved for 11b (fail-closed RuntimeError until then); one consumer (demo_data/attribution.py:170 join). KEY RESEARCH FINDING: the DTO's six occupancy fields (min/max/avg visitors_inner/outer — the sensor_visitors drift, findings Part 3) have ZERO consumers anywhere; join reads only incoming_inner_count + outgoing_outer_count; float→int policy already explicit at attribution.py:209 int(round()). So the "two queries + client-side join" the drift note assumed is avoidable: make the six fields optional (None) and query sensor_visits ONLY — half the scan cost, no second query, honest nulls instead of fake zeros. Also verified: google-adk floor 1.21.0 (SecretManagerClient needs 1.29.0 — step 6 decision to surface); live tier fixtures reusable (tests/live/conftest.py re-registers tests/integration env fixtures); probe's BlueZooProbe/QuotaExceeded pattern is scripts/-side (not importable from app/ — conformer gets its own thin HTTP layer, same guards).
