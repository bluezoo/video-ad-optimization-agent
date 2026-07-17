# Workstream 03: metrics-glossary-and-terminology

**Branch:** version_2_metrics-glossary
**Phase doc:** .docs/version2-plan/03-metrics-glossary-and-terminology.md

## Research findings

Every phase-doc claim re-verified against current code (post-workstream-02 merge, base 1fb1d77) and against the live BlueZoo API docs:

- **Metric-computation sprawl confirmed.** RPI is recomputed inline at metrics_tools.py:217, 248, 352, 554, 658, campaign_tools.py:254 (`get_campaign`), plus a SQL-level ratio-of-sums at metrics_tools.py:307; the two independently-written `_generate_mock_video_metrics()` duplicates exist at mock_data.py:168 and review_tools.py:454. No shared definition anywhere. (Exact full inventory is Phase 4's job; this confirms the premise.)
- **Schema confirmed** (db.py:141-152): `video_metrics` carries `impressions` (int), `dwell_time_seconds` (scalar REAL — one average per video/day), `circulation` (int), `revenue` (REAL).
- **BlueZoo definitions re-verified live** (api.bluezoo.io, fetched 2026-07-16, exact quotes):
  - `sensor_visits`: "measure the number of devices seen within the inner detection range of a sensor, **also known as impressions**" — the phase doc's central claim holds verbatim.
  - `sensor_dwell`: "a **distribution of visit durations per 15-minute slots**" — confirms the review correction: bins, not a scalar; no direct 1:1 mapping to our `dwell_time_seconds`.
  - `sensor_visitors`: occupancy (min/avg/max per 15-minute period) — distinct from visits, as the phase doc's table says.
- **README.md** contains the client's own operational RPI definition (line 9: POS revenue for the advertised product ÷ impressions delivered for that store's ad during a day) plus scattered metric prose (lines 31-32, 53, 57) — useful source material for the glossary.
- `docs/METRICS.md` does not exist; nothing in the repo references it yet.
- **Divergence found:** phase doc Step 2 says "Link `docs/METRICS.md` from `README.md`" — this conflicts with the standing repo rule (CLAUDE.md: README is client-facing, never edited; pointers/corrections live in SETUP_INSTRUCTIONS.md). Resolution below; phase doc to be amended with provenance.
- Bonus check: Phase 11's doc already records the BlueZoo Fetch API deprecation (11-live-bluezoo-adapter.md:22) — no amendment needed there.

## Implementation approach

Documentation-only, exactly as the phase doc (post-review) prescribes — no Python constants module, zero changes under `app/`:

1. **Create `docs/METRICS.md`** — one authoritative prose definition per metric:
   - **Impressions** = one inner-zone visit event attributed to a screen + time window; adopts BlueZoo `sensor_visits` verbatim (with the live-verified "also known as impressions" quote cited).
   - **RPI** = `total_revenue / total_impressions` over a window — **ratio of sums, never sum of ratios** (the rule Phase 4 implements as `compute_rpi()`; also includes the client's operational per-store/per-ad/per-day framing from README:9 as context).
   - **Revenue** = explicitly not a BlueZoo metric (BlueZoo measures attention, not sales); sourced from PoS/attribution (Phase 12); RPI meaningful only after the join.
   - **Circulation** = app-local synthetic metric; BlueZoo mapping **unresolved** (open question 1 restated, candidate OTS/occupancy mapping labeled unconfirmed).
   - **Dwell time** = app-local scalar average; BlueZoo `sensor_dwell` alignment **requires a bin-aggregation rule, unresolved until Phase 11**.
   - Appendix: the BlueZoo table map from the phase doc (visits/visitors/dwell/per-minute/uv/flow/pulses) with the do-not-conflate notes — including the `group_flow_*` `campaign_id` name-collision warning — so Phase 4/10/11 implementers read one doc, not the API docs from scratch.
2. **Link it where internal readers actually look** (divergence resolution): a pointer + one-paragraph summary in `SETUP_INSTRUCTIONS.md`, and a one-line pointer in `CLAUDE.md`'s project-overview section (implementation models read CLAUDE.md first). **README.md stays untouched** — its client-facing RPI prose remains, and `docs/METRICS.md` is recorded as the internal source of truth that supersedes scattered explanations. **Rejected alternative:** editing README per the phase doc's literal Step 2 — violates the standing owner rule; the rule wins.
3. **Amend the phase doc** (Step 2) with a provenance note recording the README divergence and where the links actually went.
4. **No code-comment/prompt cleanup**: agent.py:308's RPI formula stays (the LLM needs it inline); replacing scattered explanations with pointers in code is Phase 4's centralization territory. Keeps this phase's "no runtime code path touched" validation literally true.

Execution note: phase is rated **Small** (not Trivial), so subagent-driven-development applies — but as a short plan (~2 tasks: write doc, wire links + amendments).

## Test plan

- `make test` passes unchanged (no code touched) — run once before PR as the phase's own validation demands.
- Docs checks: `docs/METRICS.md` exists, contains definitions for all five metrics with circulation/dwell explicitly marked unresolved, contains no code blocks that could be mistaken for an implementation; SETUP_INSTRUCTIONS.md and CLAUDE.md link to it; `git diff` shows zero changes under `app/` and none to README.md/DEMO_GUIDE.md.
- **Demo scenario: explicitly skipped** — this phase is genuinely non-agent-facing (documentation only, no tool contract or prompt changes). Per `verifying-with-demo-scenarios`, the skip and its reason will be recorded in WORK_LOG.md rather than silently omitted.

## Out of scope

- Any change under `app/` — no constants module, no call-site edits, no prompt edits (all Phase 4).
- README.md and DEMO_GUIDE.md — untouched.
- Resolving open questions 1 (circulation↔BlueZoo mapping) and 2 (unique reach via `group_uv_*`) — the glossary records them as unresolved; answering them needs BlueZoo/client input (they stay in 99-open-questions.md).
- Any BlueZoo API integration work (Phase 11) or metric computation changes (Phase 4).
