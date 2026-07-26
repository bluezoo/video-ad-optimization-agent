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
  `distribution_median_duration`** — METRICS.md (Dwell time section) defers the histogram→scalar
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

## 2026-07-25 — checkpoint 2: working doc approved

Owner approved the six-dimension restatement: *"Yes, i think that make sense.
We will get the data soon, but before we do that, we need to make sure our
schema and system is adpated to the actual bluezoo system. We can achieve
that."* Both flagged judgment calls approved implicitly by that yes:
(1) amend the wrong-in-hindsight Q6/Q11 UV-campaign correction openly with
provenance rather than silently editing it; (2) state the zero-data limitation
bluntly and raise "tenant with real data / seed AP_599" as a client ask.
Owner's framing to carry into the work: real data is coming, so the point of
this pass is that **our schema and system are adapted to the actual BlueZoo
system before it arrives**.

## 2026-07-25 — checkpoint 3: plan — owner authorized direct execution

Owner instruction immediately after approval: *"Go ahead and update the docs
and worstreams and commit them"* — taken as approval to execute the three
deliverables exactly as enumerated in the approved working doc's
"Implementation approach" (probe script, saved scan, tenant-genericity
requirements + amendments), rather than producing a separate plan.md gate for
a three-deliverable docs+script workstream. Recorded explicitly so the
deviation from the usual writing-plans step is visible, not silent. Execution
is inline (CLAUDE.md trivial-phase fast path), with incremental commits per
deliverable.

## 2026-07-25 — checkpoint 4: deliverables 1 + 2 (probe script, saved scan)

- `scripts/bluezoo_probe.py` — read-only tenant probe. Env-driven
  (`BLUEZOO_ACCESS_KEY`, `BLUEZOO_BASE_URL`) so it runs against any BlueZoo
  customer, not just ours. Guards the undocumented mandatory time filter
  *before* sending, picks the right time column per table
  (`timestamp`/`date`/`date_start`), skips non-entitled tables rather than
  failing, never prints or persists the key.
- `working-docs/bluezoo-live-verification/scan/{scan.json,scan.md}` — produced
  by actually running it against Apollo / AP_599: 19 tables, every column and
  type, all 6 sampled tables at 0 rows (stderr NOTE emitted).
- `tests/unit/test_bluezoo_probe.py` — 16 tests, 0.02s, no network. Pins the
  tenant-variable behaviors specifically: BlueZoo's own published example query
  is refused by the guard; each of the four time columns is accepted; a missing
  optional table is skipped not errored; zero rows is a valid answer; the scan
  output never contains the key.
- 3 ruff findings fixed (`datetime.timezone.utc` → `datetime.UTC` et al);
  lint clean, tests re-verified 16/16.

## 2026-07-25 — checkpoint 5: deliverable 3 (findings + amendments)

`findings.md` written as the durable record, then provenance amendments applied
to **pending phases only**, per the owner's constraint:

- `11-live-bluezoo-adapter.md` — the substantive one. 11b's last outstanding
  validation item ("authenticated drift check") marked **done**, plus nine
  build rules each traced to a live observation, the `BlueZooVisitInterval`
  two-table drift handed to 11b as a design decision, and the zero-rows limit
  called out as blocking `CachedBlueZooAudienceDataSource` outright. Also
  corrected the Dependencies line, which claimed the drift check was still
  pending.
- `12-live-pos-adapter.md` / `13-production-hardening-live-mode.md` — narrower:
  per-tenant configuration as a precedent (12), and secrets holding a
  `{base_url, access_key}` pair plus wrong-cluster-vs-bad-credential error
  ambiguity (13).
- `99-open-questions.md` — Q2 (ask (b) closed; REST proven, transport now a
  decision), **Q6 corrected openly** (the UV campaign-column reversal, with the
  surviving `ad_campaign_id` rationale), Q11 answered (`group_sensor_history`),
  Q12 answered-but-inverted (access granted, data absent — now the top ask),
  Q17 narrowed (fallback (b) entitled here), Q18 halved, closing paragraph
  updated.
- `working-docs/replan-data-track/bluezoo-mapping-verification.md` — pointer
  from its "remaining unknowns" section, and an explicit note that its must-fix
  #2's prose-correction half is overturned (rename half stands).
- `docs/METRICS.md` — the deferred dwell histogram→scalar rule: BlueZoo ships
  `distribution_average_duration`/`distribution_median_duration`, so the rule is
  a direct read; units still unverified with zero rows.

**Decision recorded:** merged phases (5, 10, 11a) were left untouched even
where this scan bears on their content — the owner scoped amendments to pending
workstreams. Where a merged phase's instruction is now wrong (ws05 port
correction #2's prose half), the correction lives in the shared verification
record and Q6, both of which a reader of that instruction reaches.

## 2026-07-25 — checkpoint 6: code review round

Full-branch review dispatched. It cross-checked every schema assertion against
`scan/scan.json` and confirmed the load-bearing ones — including the Q6
reversal — but found three real factual errors and one gap. All verified
independently against the artifact before fixing:

- **DISCOVERY (correction to our own finding): `group_convert` was never an
  "extra."** It appears in the documented `list_tables` inventory
  (`bluezoo-mapping-verification.md`, last bullet) — we listed it as newly
  discovered. Worse, we missed the mirror-image fact: **`group_dwell` is
  documented but NOT entitled on this account.** The arithmetic closes exactly
  (14 documented − 1 absent + 6 extras = 19), and the absence is the *stronger*
  evidence for the tenant-genericity rule: entitlements are not a superset of
  the docs, so "documented" is not a floor a connector may assume. Corrected in
  `findings.md`, `11-*.md`, `99-open-questions.md`,
  `bluezoo-mapping-verification.md`, and marked (not erased) in `working-doc.md`.
- **"The `group_convert*` family carries `date_start`" is false for one of four
  —** `group_convert_daily` has only `date`. The code was never affected
  (`time_column_for` discovers the column), but the prose told 11b to hardcode
  a table→column map. Rewritten as "read the column from the schema, never
  hardcode," which is the safer rule anyway.
- **"`sensor_visits` matches our port exactly" was overstated** — it matches
  BlueZoo's *published column list* exactly; our mimic deliberately renames
  identity columns per ws05's naming policy. Both statements are true; only the
  second was written. Reworded, since `findings.md` Part 3 argues the port
  *diverges* two sections later.
- **`app/demo_data/BLUEZOO_MAPPING.md:26` still asserted the refuted UV claim.**
  It is a shipped repo doc, not a phase doc, so the "pending workstreams only"
  constraint doesn't reach it — and we had already amended two other merged
  shared records on that reasoning. Amended in place with a pointer to
  `findings.md`. This is the only `app/` file this workstream touches, and it is
  documentation.
- **Evidence provenance made explicit.** Four claims (host aliasing, the
  BigQuery error text, the time-constraint message, SELECT-only) are properties
  of *rejected* calls and so cannot appear in a successful scan; `findings.md`
  now says which claims the artifact backs and which come from the checkpoint-1
  manual calls. Notably **SELECT-only was never tested** — verifying it would
  have meant attempting a write against a customer account. Now labelled as
  inherited from BlueZoo's published guarantee rather than "Confirmed."

Code changes from the same round: client-side non-SELECT refusal in
`BlueZooProbe.query` (makes "read-only" a property of the class, not a promise
about call sites — the guard is earmarked for reuse in 11b); honest docstring
about the time-guard being a best-effort scan rather than WHERE-clause parsing;
`BlueZooError` wrapping for non-JSON responses and malformed `list_tables`
(likeliest real failure when pointed at a wrong cluster); `count_window`
recorded in the scan artifact so "0 rows" is self-describing; count extraction
no longer able to synthesize a 0.

`FakeProbe` now overrides `_call` instead of `query`, so tests exercise the real
guards rather than a copy that could drift. Tests 16 → 20 (non-SELECT refusal
×3, partial-`desc_table`-failure scan). Scan re-run live: byte-identical
schemas/tables/counts to the committed artifact, differing only by the new
`count_window` field — an incidental reproducibility check.

Env vars documented in `SETUP_INSTRUCTIONS.md` (the working doc promised
"`app/.env.example`-style documentation"; no such file exists in this repo, and
`SETUP_INSTRUCTIONS.md` is where CLAUDE.md says setup belongs).

Not actioned: the reviewer flagged a missing `STATUS.md` row, but the row exists
on `version_2` (`192dd40`) — STATUS.md is single-writer in the main checkout, so
the worktree's copy is simply behind. 11b's note there does need refreshing;
done in the main checkout, not on this branch.
