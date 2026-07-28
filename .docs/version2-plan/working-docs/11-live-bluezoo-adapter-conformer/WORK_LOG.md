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

## 2026-07-27 — DISCOVERY: the phase doc's "two queries + client-side join" premise is wrong
Assumed (11-live-bluezoo-adapter.md, live-verification drift note): a conformer populating today's DTO must query both sensor_visits and sensor_visitors and join client-side on (sensor_id, timestamp).
Actual: the six occupancy fields (minimum_/maximum_/average_visitors_inner/outer) have ZERO consumers — writers only (app/demo_data/seed.py:155-159) plus one presence-assertion in test_demo_seed.py; the attribution join reads only incoming_inner_count + outgoing_outer_count. Owner verified independently and confirmed. The second query would double metered scan cost to populate values nothing reads.
Resolution (approved): six fields become `float | None = None` (demo still populates; connected rows carry None, divergence documented IN THE MODEL per owner condition); live conformer queries sensor_visits only. Circulation safe — demo derivation uses outgoing_outer_count (sensor_visits, live-populated).
Blast radius amended with provenance: 11-live-bluezoo-adapter.md (drift note), docs/METRICS.md (circulation entry), 99-open-questions.md (Q5).

## 2026-07-27 — checkpoint 2: working doc approved (with conditions)
Owner approved the six-dimension restatement and all three flagged decisions:
1. REST-first — confirmed; recorded as OUR assumption, not client instruction; BigQuery later = second class behind same one-method interface.
2. Drop CachedBlueZooAudienceDataSource — confirmed; redacted real MO_92 response as fast-tier fixture replaces it ("real-payload validation in the fast tier, which the cached provider never would"); Exit criteria amended with provenance, not left silently unmet.
3. Secrets: app/.env + documented deploy-time injection — confirmed; GSM/ADK SDK stays Phase 13 (already Tier B there, not a launch blocker). CONDITION: Phase 13's amendment must require secrets to hold a {base_url, access_key} PAIR per tenant, not a lone key (separating them turns "wrong host" into a support ticket reading "auth is broken"); SETUP_INSTRUCTIONS must document the pair explicitly with a CONCRETE `gcloud run deploy --set-secrets` line, not prose.
Two conditions on the DTO change (owner-added): (a) the demo-vs-connected divergence documented in the model itself (field comments/docstring: demo-populated, None in connected mode, because populating costs a second table scan for values nothing reads); (b) DISCOVERY protocol run — done, see entry above.
Reminder restated: demo-scenario verification + DEMO_GUIDE.md journeys are mandatory.

## 2026-07-27 — checkpoint 3: plan approved (with amendments)
Owner approved the 11-task plan ("Live cost is fine, proceed") with two plan amendments + one property to preserve, all folded in before execution:
1. Condition (b) DISCOVERY protocol: ALREADY EXECUTED at working-doc approval (commit ffdfb43 — WORK_LOG DISCOVERY entry + provenance amendments in 11-*.md drift note + Exit criteria, METRICS.md circulation, Q5). Added Task 11 Step 1b verifying all amendments are in the branch diff pre-PR, per owner's "add it to the task list explicitly."
2. BLUEZOO_SENSOR_MAP sensors chosen from EVIDENCE (new Task 6 Step 0): MO_92 recent grid coverage ~34%, 19 live sensors valid=false — select top valid-row producers over the last 7 days via a group-by query (~20 KB), record ids/counts/rationale in the fixture provenance note; Task 7 + Task 9 consume the verified ids.
3. Singleton must not cache construction failure (owner-named property): new factory test test_construction_failure_is_not_cached — failed connected construction, then fixed env, succeeds WITHOUT reset.
Plan: working-docs/11-live-bluezoo-adapter-conformer/plan.md. Execution: subagent-driven-development.
