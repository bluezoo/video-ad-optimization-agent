# Workstream bluezoo-live-verification — WORK_LOG

Non-numbered workstream (like `replan-data-track`): no phase doc of its own.
Scope: authenticated live verification of BlueZoo's Data Warehouse API against
our mimic, using the owner's new account, plus a committed read-only probe
script. Amends the pending phases only (11b, 12, 13) and the shared records
(`working-docs/replan-data-track/bluezoo-mapping-verification.md`,
`99-open-questions.md`).

## 2026-07-25 — checkpoint 1: kickoff, worktree created

- Worktree `.claude/worktrees/version_2_bluezoo-live-verification`, branch
  `version_2_bluezoo-live-verification`, base `version_2` @ 5db91bc (post-ws16
  merge). Base verified via merge-base.
- Dependencies: none in the code sense. All numbered phases through 16 are
  merged except 11b/12/13, which this workstream informs rather than depends on.
- Owner context: BlueZoo account provisioned (org "Walmart Demo", Cluster/Account
  **Apollo / AP_599**, role Super Admin). Owner directive, verbatim: "we need to
  make sure we are super alinged in bluezoo connectors so that our agents can
  work with any of their customer is very crucual. So running a pass and saving
  the results of full scan of db is important. we can keep it seeprate and then
  odify our workstreams to adpat to the changes. Only the workstreams which are
  pending." Owner chose Option C (tracked lightweight workstream) over scratch
  scripts in a gitignored dir or a full numbered phase.
- Pre-kickoff probe findings (6 read-only calls, made in the review session
  before this worktree existed; to be re-run properly by this workstream's
  script):
  1. Auth works: `Authorization: AccessKey <key>` → HTTP 200.
  2. Host is CLUSTER-scoped, not canonical: `hermes.apollo.bluezoo.io` and
     `apollo-api.bluefoxengage.com` are aliases (identical 200s);
     `morpheus-api.bluefoxengage.com` → `BAD_TOKEN` (different cluster).
  3. SQL dialect confirmed BigQuery (verbatim `invalidQuery: Unrecognized name:
     … at [1:164]` error text) — was inference, now fact.
  4. UNDOCUMENTED mandatory constraint: `run_query` rejects any query without a
     `date_start`/`date_end`/`timestamp` WHERE filter — BlueZoo's own documented
     example (`select * from sensor_visitors limit 1`) would fail.
  5. 19 tables on this account, not the documented 14 — including
     `sensor_visitors_per_minute` (Q17 fallback (b) available without asking),
     four `group_convert*` tables, `group_sensor_history`, `group_uv_quarterly`.
     `group_convert` carries BlueZoo's own `campaign_id` (flow-campaign),
     confirming the ws05 `ad_campaign_id` rename was correct.
  6. Account has ZERO data: every table queries cleanly, 0 rows across
     2020-2026. `desc_table` works regardless, so structure is verifiable but
     values (bin scale, `valid` semantics, day-cut timezone, magnitudes) are not.
- Phase-doc research: pending (appended to this entry when Step 2 completes).

## 2026-07-25 — checkpoint 1 amendment: kickoff research done

Authenticated full `desc_table` scan of all 19 tables completed (raw JSON in
scratch; the committed probe script will reproduce it). Findings digest in
`working-doc.md`. Headlines beyond the six pre-kickoff probe results:

- **Mimic vindicated where it counts:** `sensor_visits` column list matches our
  port exactly; `sensor_dwell` has exactly 106 HHMM-encoded bins including
  `_0058_to_0100` and `_2400_to_beyond` — ws05 port correction #1 confirmed
  against live schema.
- **`group_uv_daily` DOES carry `campaign_id` + `campaign_name`** (and `cuv`).
  This CONTRADICTS the 2026-07-16 published-docs conclusion recorded in Q6/Q11
  ("UV tables are group_id-keyed, no campaign column, contrary to the donor
  spec") — the donor spec was right; our correction of it was wrong. Needs a
  provenance amendment.
- **`group_sensor_history` (group_id, group_name, sensor_id, sensor_name,
  timestamp) is the group↔sensor mapping table** — Q11 has a real,
  API-discoverable answer; membership is timestamped, so it varies over time.
- **`sensor_dwell` exposes `distribution_average_duration` /
  `distribution_median_duration`** — METRICS.md:45 defers the histogram→scalar
  dwell rule to Phase 11 pending a real response; BlueZoo ships the scalar, so
  the rule is "read it, don't derive it."
- **`time_zone` STRING exists on every sensor table** alongside the documented
  `time_offset` (presence proven; behavior unprovable with zero rows).
- **Our own drift:** `app/models/attribution.py:43` `BlueZooVisitInterval`
  carries `minimum_/maximum_/average_visitors_*`, which live on `sensor_visitors`
  — violating ws05 port correction #5 ("scope the DTO to sensor_visits fields
  only"). Live schema confirms two tables ⇒ a live conformer needs two queries
  joined client-side. Recorded for 11b, deliberately not fixed here.

Dependencies re-checked against STATUS.md (not phase-doc narrative): phases
1-10, 11a, 14a/14b, 15, 16 all `merged`; 11b/12/13 `not started`. Nothing this
workstream depends on is outstanding.
