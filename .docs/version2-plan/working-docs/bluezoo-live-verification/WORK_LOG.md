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
