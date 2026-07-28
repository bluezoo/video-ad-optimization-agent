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

## 2026-07-27 — checkpoint 7: second tenant WITH REAL DATA (MO_92)

Scope extension, owner-approved mid-PR. BlueZoo granted access to a second
account after we raised the zero-data ask: org "Hotels International",
cluster/account **Morpheus / MO_92**, their **staging** environment at
`https://hermes.morpheus.bluezoo.io/v2/dwh`. 5.1M rows in `sensor_visits`, 101
sensors, 2021-03 → current. Owner directive: fold it into this PR, keep the
docs current.

**Cluster-scoping confirmed the hard way:** the Apollo AccessKey returns
`BAD_TOKEN` on Morpheus; each cluster issues its own key. Credentials are
cluster-scoped, not user-scoped — stronger than what Part 2 #1 claimed.
Entitlements are *identical* across the two tenants (same 19 tables, same
`group_dwell` absence), which strengthens the tenant-genericity rules.

### DISCOVERY (the big one): a metered bytes-scanned quota, and I exhausted it

Round 1 ran full-history aggregates across all 101 sensors — the habit formed
on AP_599, where scans were free because the tenant was empty. On a populated
tenant that cost an estimated **735 MB** and hit:

> `You've reached your monthly fair use limit of 1GB data scanned per sensor.`

Afterwards *every* `run_query` failed, including a single-sensor single-day
one. Metadata and the Real-time API stayed up. There is no endpoint to check
remaining allowance and no bytes-scanned metadata in responses.

Reported to the owner immediately; BlueZoo reset it. **This is the most
consequential finding of the workstream** — it is an architectural constraint
on Phase 11b's access pattern, not a footnote. Amended into `11-*.md` (build
rules), `13-*.md` (new Tier B operational state + runbook), Q18,
`SETUP_INSTRUCTIONS.md`, and the probe itself.

### Owner challenge, and a course correction worth recording

Owner asked, in substance: *why are we fetching data at all — isn't the goal to
understand the schema, and isn't schema free?* Largely right, and the answer
sharpened the plan:

- Schema **is** free (`desc_table`) and we already had it; the workstream's
  original goal was met before any `run_query`.
- A narrow band of questions genuinely needs *values*, not schema — bin scale,
  `valid` semantics, whether `campaign_id` is populated. Schema gives the field,
  not its meaning, and these change computed numbers rather than field names.
- **The real error was running a census where a specimen would do.** Every one
  of those questions was answerable from a few hundred rows.

Owner approved a bounded plan: four small samples, ~1 MB expected. Executed
cheapest-risk-first with a 0.08 MB canary query after each risky one. **Round 2
cost under 3 MB and answered more than round 1's 735 MB did.**

### What round 2 established (full detail in `findings.md` Part 5)

- **Dwell: bins are 0–100 percentages**, not 0–1 shares (a 100× error avoided);
  `distribution_average_duration`/`_median_duration` are **integer seconds**, a
  1:1 map onto `dwell_time_seconds`; **when `distribution_weight = 0.0` both
  scalars are NULL** while `total_visits` is non-zero, so null dwell is
  legitimate and must be carried, not coerced to 0. `docs/METRICS.md`'s
  long-deferred aggregation rule is now settled.
- **`valid` is half the data and 72% of all counts**, with a *higher* average
  than valid rows, plus an undocumented `null` third state. Per-sensor, not
  per-slot, and it flips over a sensor's lifetime. `(sensor_id, timestamp)` is
  unique so there is no double-count risk. Excluding it swings impressions ~4× —
  now the highest-value question for BlueZoo, and explicitly *not* something to
  default silently.
- **Tables are dense**: exactly 96 slots/sensor/day including zeros, so a
  missing row is a sensor outage rather than a quiet period.
- **`group_sensor_history`** (Q11): 75 groups / 93 sensors / 1,181 rows,
  snapshot-versioned — read as-of a date, never static.
- **`group_uv_daily.campaign_id`** (Q6): populated in 94% of rows, ~1:1 with
  `group_id`, with `target_uv`/`actual_accuracy` — a BlueZoo *UV-measurement*
  campaign, not an advertising one. Settles the caveat the Q6 reversal left
  open and makes `ad_campaign_id` unambiguous.
- **`sensor_visitors_per_minute` is entitled but DORMANT** — 2.8M historical
  rows, zero in all of 2026. Weakens Q17 fallback (b), and yields a connector
  rule: **entitlement ≠ population.**
- **Magnitudes** captured for demo calibration.

### Decisions recorded

1. **Customer-data restraint.** MO_92 holds a real hotel operator's venues and
   traffic. `findings.md` quotes two venue names BlueZoo themselves disclosed in
   writing plus numeric magnitudes, and deliberately does **not** reproduce the
   93-sensor inventory. Committed artifacts (`scan-mo92/`) are schema and row
   counts only — verified to contain no venue names, no traffic, no key.
2. **Probe hardened so this cannot recur**: default count window is the last 30
   days (`--full-history` is opt-in and documented as unsafe on a populated
   tenant); `QuotaExceeded` is its own exception with exit code 2;
   `row_width_bytes()` exposes the `select *` trap; the scan records
   `select_star_bytes_per_row`; a `COST NOTE` names the widest table. Tests
   20 → 26.
3. The old top-priority client ask ("give us real data") is **granted and
   closed**; `findings.md`'s asks section was rewritten around what actually
   remains.
