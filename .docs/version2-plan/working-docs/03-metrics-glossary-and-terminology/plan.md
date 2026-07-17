# Workstream 03: Metrics Glossary & Terminology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `docs/METRICS.md` as the single authoritative glossary for impressions, RPI, revenue, circulation, and dwell time, linked from SETUP_INSTRUCTIONS.md and CLAUDE.md.

**Architecture:** Documentation only — one new markdown file plus two pointer edits and one phase-doc provenance amendment. Zero changes under `app/`; no constants module (the phase doc's own review correction forbids it).

**Tech Stack:** Markdown. Verification via grep/git-diff checks and an unchanged `make test`.

## Global Constraints

- Branch `version_2_metrics-glossary`, worktree `.claude/worktrees/version_2_metrics-glossary`.
- **Zero changes under `app/`** — this phase touches no runtime code path; `make test` must pass unchanged.
- **README.md and DEMO_GUIDE.md are never edited** (owner-approved divergence from the phase doc's literal Step 2: links go in SETUP_INSTRUCTIONS.md + CLAUDE.md instead).
- `docs/METRICS.md` contains **no fenced code blocks** — definitions are prose; the only executable expression of a definition will be Phase 3's `compute_rpi()`.
- Circulation and dwell time are written as **"BlueZoo mapping unresolved"** — do not upgrade the candidate mappings to fact.
- No `Co-Authored-By: Claude` or AI-attribution trailers in commits.

## File Map

| File | Task | Change |
|---|---|---|
| `docs/METRICS.md` | 1 | Create — the glossary (full content below) |
| `SETUP_INSTRUCTIONS.md` | 2 | New "Metrics glossary" section after "## Environment" area (see exact placement) |
| `CLAUDE.md` | 2 | One pointer sentence in "## Project overview" |
| `.docs/version2-plan/03-metrics-glossary-and-terminology.md` | 2 | Provenance amendment on Step 2 (README divergence) |

---

### Task 1: Create `docs/METRICS.md`

**Files:**
- Create: `docs/METRICS.md`

**Interfaces:**
- Produces: `docs/METRICS.md` at exactly that path — Task 2's links and Phase 3's plan reference it by this path.

- [ ] **Step 1: Create the file with exactly this content**

````markdown
# Metrics Glossary

**This is the single source of truth for what every metric in this app means.** Read it before touching any metric-related code. Phase 3 (`.docs/version2-plan/04-centralize-rpi-metrics.md`) turns the RPI rule below into the one shared implementation (`compute_rpi()`); until then, no code file is authoritative — this document is.

Definitions are aligned to BlueZoo's own vocabulary wherever BlueZoo defines the term (quotes below were verified against the live BlueZoo Data Warehouse API docs at `api.bluezoo.io`, fetched 2026-07-16). Where a mapping is *not* confirmed, this document says so explicitly rather than guessing.

## Impressions

**One inner-zone visit event, attributed to a specific screen (sensor) and time window.**

This adopts BlueZoo's definition verbatim — BlueZoo's `sensor_visits` table is captioned: "Sensor Visits measure the number of devices seen within the inner detection range of a sensor, **also known as impressions**." An impression is an *event count* (a device entered the inner detection zone), not an occupancy snapshot and not a deduplicated person count — see the appendix for the neighboring concepts it must not be conflated with.

In this app: the `video_metrics.impressions` column (one integer per activated video per day).

## Revenue

**The point-of-sale revenue for the advertised product, at the store showing the ad, over the same time window as the impressions it is paired with.**

Revenue is **not a BlueZoo metric** — BlueZoo sensors measure audience attention, not sales. Revenue enters the system from a separate source (point-of-sale data or an attribution model; see `.docs/version2-plan/12-live-pos-adapter.md`). RPI is only meaningful once both sides — BlueZoo impressions and PoS revenue — are joined over the same product, store, and window.

In this app: the `video_metrics.revenue` column (mock-generated in demo mode).

## Revenue per Impression (RPI)

**RPI = total revenue ÷ total impressions, computed over a given window.**

This is the app's primary KPI, and it is BlueZoo's own coined, marketed metric. The client's operational framing (from the project README): retailers normalize each store's point-of-sale revenue for the advertised product by the number of impressions delivered for that store's ad during a day.

**The one non-negotiable computation rule: RPI over any multi-period window is the *ratio of sums, never the sum (or average) of per-period ratios*.** A weekly RPI is sum(revenue over the week) ÷ sum(impressions over the week) — it is *not* the sum or mean of seven daily RPI values. Summing ratios produces a number with no meaning (this exact bug existed in the weekly bar chart and is fixed by Phase 3's centralization). Any code that aggregates RPI across days, videos, campaigns, or stores must recompute from the summed numerator and denominator.

Derived convenience form: revenue per 1,000 impressions (`RPI × 1000`, a CPM-style figure) — same rule applies.

## Circulation

**App-local synthetic metric; BlueZoo mapping unresolved.**

The `video_metrics.circulation` column exists in this app's schema and is populated by the demo-mode mock generator, but it has **no confirmed BlueZoo counterpart**. Candidate interpretation (unconfirmed): broader foot-traffic / opportunity-to-see near a screen — possibly BlueZoo `sensor_visitors` occupancy or an outer-zone visit count — as distinct from impressions (inner-zone attention). That is a plausible retail-signage-industry pattern (circulation = OTS, impressions = actual attention) but it has **not been confirmed against BlueZoo's docs or the client's own usage**. Do not build anything on the candidate mapping; see open question 1 in `.docs/version2-plan/99-open-questions.md`.

## Dwell time

**App-local scalar average; BlueZoo alignment requires an aggregation rule, unresolved until Phase 10.**

This app's `video_metrics.dwell_time_seconds` column stores **one scalar average per video per day**. BlueZoo's `sensor_dwell` is *not* that: it is "a distribution of visit durations per 15-minute slots" — i.e., visit-duration *bins*, not a single number. Mapping the distribution onto our scalar requires a defined, documented aggregation rule (e.g., a weighted mean across bins) that must be validated against a real BlueZoo response before it is written down as fact — that validation belongs to Phase 10 (`.docs/version2-plan/11-live-bluezoo-adapter.md`). Until then, treat our column as demo-mode synthetic data with intentionally unresolved provenance.

## Appendix: BlueZoo table map (do-not-conflate notes)

| BlueZoo table | What it measures | Relationship to this app |
|---|---|---|
| `sensor_visits` | Inner-zone visit counts — "also known as impressions" (BlueZoo's own caption) | **= our impressions.** The one confirmed 1:1 mapping. |
| `sensor_visitors` | Occupancy (min/avg/max) per 15-minute period | *Not* visits: occupancy is a point-in-time count, visits are events. Candidate (unconfirmed) relative of circulation. |
| `sensor_dwell` | Distribution of visit-duration bins per 15-minute slot | No direct mapping to our scalar `dwell_time_seconds` — needs an aggregation rule (Phase 10). |
| `sensor_visitors_per_minute` | Fine-grained occupancy time series | Unused today; candidate input for playout attribution (Phase 9). |
| `group_uv_daily/weekly/monthly/custom` | Unique visitor counts, deduplicated over a period | "Unique reach" — a *different* metric from impressions; never conflate deduplicated visitors with visit counts. See open question 2. |
| `group_flow_transition/correlation/duration/segmentation` | Cross-zone traffic-flow journeys | Carries a `campaign_id` field that is **BlueZoo's own "flow campaign" concept — unrelated to this app's ad campaigns.** When mapping BlueZoo data, never reuse the bare name `campaign_id` for this app's ad-campaign id; pick a distinct field name (e.g. `ad_campaign_id`) to avoid collision. |
| `sensor_pulses` | Sensor telemetry/health (uptime, connectivity) | Not audience data — must never appear in any impressions/revenue rollup. |
````

- [ ] **Step 2: Verify the file's structural requirements**

Run: `test -f docs/METRICS.md && grep -c "^## " docs/METRICS.md && grep -n "unresolved" docs/METRICS.md | head -4 && (grep -n '```' docs/METRICS.md && echo "FAIL: fenced code block present" || echo "no code blocks: OK")`

Expected: file exists; 6 `##` sections (5 metrics + appendix); "unresolved" appears in both the Circulation and Dwell time sections; "no code blocks: OK".

- [ ] **Step 3: Commit**

Run:
`git add docs/METRICS.md`
`git commit -m "Add docs/METRICS.md: authoritative BlueZoo-aligned metrics glossary"`

---

### Task 2: Wire links, amend the phase doc, prove zero behavior change

**Files:**
- Modify: `SETUP_INSTRUCTIONS.md` (insert new section between "## Run locally" and "## Test")
- Modify: `CLAUDE.md` ("## Project overview", after the "Key source layout" paragraph)
- Modify: `.docs/version2-plan/03-metrics-glossary-and-terminology.md` (Step 2 provenance amendment)

**Interfaces:**
- Consumes: `docs/METRICS.md` from Task 1 (exact path).

- [ ] **Step 1: Add the SETUP_INSTRUCTIONS.md section**

Insert immediately before the line `## Test`:

```markdown
## Metrics glossary

`docs/METRICS.md` is the single source of truth for what every metric means (impressions, RPI, revenue, circulation, dwell time), aligned to BlueZoo's own vocabulary — read it before touching any metric-related code. It supersedes the metric explanations scattered through code comments and the README's marketing prose; where they disagree, `docs/METRICS.md` wins. (README.md itself stays untouched per this file's header note.)

```

- [ ] **Step 2: Add the CLAUDE.md pointer**

In `CLAUDE.md`, immediately after the paragraph beginning `Key source layout:` (still inside "## Project overview"), insert as its own paragraph:

```markdown
`docs/METRICS.md` is the authoritative glossary for every metric (impressions, RPI, revenue, circulation, dwell time) — read it before changing metric-related code; code comments and README prose do not override it.
```

- [ ] **Step 3: Amend the phase doc's Step 2 with provenance**

In `.docs/version2-plan/03-metrics-glossary-and-terminology.md`, directly below the line `2. Link docs/METRICS.md from README.md, replacing any ad-hoc metric explanations currently scattered in code comments.` add:

```markdown
   > **Amended (workstream 03, 2026-07-16):** README.md is client-facing and stays untouched per the repo's standing rule (CLAUDE.md "Repo etiquette"), so the link went into `SETUP_INSTRUCTIONS.md` (new "Metrics glossary" section) and `CLAUDE.md` (project-overview pointer) instead. Code-comment/prompt cleanup is deferred to Phase 3's centralization — this phase changed nothing under `app/`, keeping the "no runtime code path touched" validation literally true.
```

- [ ] **Step 4: Verify zero behavior change and link integrity**

Run: `git diff --name-only version_2...HEAD -- app/ README.md DEMO_GUIDE.md` — expected: **empty output**.
Run: `grep -n "METRICS.md" SETUP_INSTRUCTIONS.md CLAUDE.md | wc -l` — expected: ≥ 2.
Run: `make test` — expected: passes identically to the version_2 baseline (unit suite green; integration 5 passed — needs the worktree venv with `google-adk[eval]`; if the venv isn't set up yet, create it first: `python3.12 -m venv .venv && .venv/bin/pip install -r app/requirements.txt && .venv/bin/pip install "google-adk[eval]"` and copy `app/.env` from the main checkout).

- [ ] **Step 5: Commit**

Run:
`git add SETUP_INSTRUCTIONS.md CLAUDE.md .docs/version2-plan/03-metrics-glossary-and-terminology.md`
`git commit -m "Link metrics glossary from SETUP_INSTRUCTIONS and CLAUDE.md; amend phase doc"`

---

## Verification & finish (lifecycle, not plan tasks)

- **Demo scenario: explicitly skipped** — docs-only phase, no agent-facing change; record the skip + reason in `WORK_LOG.md` (checkpoint 5) per `verifying-with-demo-scenarios`.
- `requesting-code-review` on the whole branch (focus: glossary accuracy vs. the phase doc's definitions and the live-verified BlueZoo quotes; constraint compliance).
- `finishing-a-development-branch`: PR into `version_2` linking the phase doc; owner-confirmed merge; STATUS/WORK_LOG finish.
