# Version 2 Workstream Status

Cross-workstream index, owned by the `tracking-workstream-progress` skill. **Read this before starting or resuming any phase** — it's the source of truth for what's actually done, not what a phase doc's own narrative claims.

Update rows in place as a workstream progresses; don't append new rows for the same phase. See `tracking-workstream-progress`'s `SKILL.md` for the full checkpoint list and the companion per-workstream `working-docs/<NN>-<name>/WORK_LOG.md`.

**Status values:** `not started` · `kickoff in progress` · `plan in progress` · `implement in progress` · `verify in progress` · `PR open` · `merged` · `discarded`

**Numbering:** phase number = doc filename prefix (Phase 7 ↔ `07-rpi-across-creatives-chart.md`). Phases start at 1; `00-overview.md` is the overview, not a phase. Renumbered 2026-07-16 (workstream replan-data-track) from the old 0-based scheme, so anything written before then — merged PR #1–#4 titles/discussions, old commit messages — may use old phase numbers, which are one less than today's. The **Doc** column stays as the explicit mapping; workstream folders under `working-docs/` and worktree/branch names use the doc prefix, which now equals the phase number.

| Phase | Doc | Name | Status | Branch | PR | Last updated | Note |
|---|---|---|---|---|---|---|---|
| 1 | `01` | emergency-model-currency-fix | merged | version_2_model-currency-fix | [#1](https://github.com/bluezoo/video-ad-optimization-agent/pull/1) | 2026-07-14 | merged 9f12738; incl. conftest fix + preview-model probe |
| 2 | `02` | bug-fixes-and-cleanup | merged | version_2_bug-fixes-and-cleanup | [#2](https://github.com/bluezoo/video-ad-optimization-agent/pull/2) | 2026-07-16 | merged e0a0a52; incl. DB-isolation fix + test de-vacuation discoveries |
| 3 | `03` | metrics-glossary-and-terminology | merged | version_2_metrics-glossary | [#3](https://github.com/bluezoo/video-ad-optimization-agent/pull/3) | 2026-07-16 | merged 2bb2452; docs/METRICS.md is the metrics source of truth; demo skipped by design (docs-only) |
| 4 | `04` | centralize-rpi-metrics | merged | version_2_centralize-rpi-metrics | [#4](https://github.com/bluezoo/video-ad-optimization-agent/pull/4) | 2026-07-16 | squash commit a29f182; demo F2 PASS; final review clean |
| 5 | `05` | deterministic-demo-data | merged | version_2_deterministic-demo-data | [#6](https://github.com/bluezoo/video-ad-optimization-agent/pull/6) | 2026-07-18 | squash-merged as a5a0f17; F2+F3 demo scenarios PASS; final review clean |
| 6 | `06` | app-mode-config-skeleton | merged | version_2_app-mode-config | [#7](https://github.com/bluezoo/video-ad-optimization-agent/pull/7) | 2026-07-19 | squash-merged as 2e05f9d; smoke-matrix verification (demo scenario skipped by design — no agent-facing change); final review zero findings |
| 7 | `07` | rpi-across-creatives-chart | merged | version_2_rpi-chart | [#8](https://github.com/bluezoo/video-ad-optimization-agent/pull/8) | 2026-07-19 | squash-merged as 60ac50f; F3 (updated criteria) + new F4 PASS; final review clean; incl. numpy-AE deploy fix |
| 8 | `08` | product-schema-generalization | merged | version_2_product-schema | [#9](https://github.com/bluezoo/video-ad-optimization-agent/pull/9) | 2026-07-21 | squash-merged as 5d3e1f8; F1.1/F2.1 regression + new F5 PASS; final review clean; owner manual test (user-journey guide) passed — 2 findings routed to Phases 9/15 via DISCOVERY amendments |
| 9 | `09` | prompt-and-agent-generalization | merged | version_2_prompt-generalization | [#10](https://github.com/bluezoo/video-ad-optimization-agent/pull/10) | 2026-07-22 | merged 20d7347 (squash); archetype registry + ad style policy; demo verify PASS (F1 2/2, F5 2/2); spawned Phase 16 (Q19 resolved), amended Phase 15 |
| 10 | `10` | playout-attribution | merged | version_2_playout-attribution | [#11](https://github.com/bluezoo/video-ad-optimization-agent/pull/11) | 2026-07-22 | squash debd5a4; owner manual test round all-pass; carried minors noted in 11-*.md |
| 11a | `11` | audience-provider-seam (port) | merged | version_2_live-bluezoo-adapter | [#12](https://github.com/bluezoo/video-ad-optimization-agent/pull/12) | 2026-07-22 | squash 4e0ce6a; F3+F4 + fail-closed smoke PASS, final review clean; ws10 items 1+2 done; testing journeys moved to root DEMO_GUIDE.md (owner rule change) |
| 11b | `11` | live-bluezoo-adapter (conformer) | not started | - | - | 2026-07-27 | depends on 11a; Q2's mimic-validation half is **fully closed** — live authenticated scan done (workstream bluezoo-live-verification), REST proven working, build rules in `11-*.md`. **Q12 now closed too**: MO_92 (Morpheus staging) has 5.1M real rows, so `CachedBlueZooAudienceDataSource` is unblocked. Read `11-*.md`'s Part 5 amendment before designing queries: dwell and `campaign_id` semantics are **settled**, a metered bytes-scanned quota shapes the access pattern, and **`valid` is quantified but NOT settled** — excluding `valid=false` swings impressions ~4×, so the exclusion rule is a live decision this phase must make explicitly, not an answered question. Remaining blockers: Q1/Q2's transport *decision*, and the `valid` rule (Q18) |
| 12 | `12` | live-pos-adapter | not started | - | - | 2026-07-27 | depends on Phases 4, 6, **11b** (11a merged; 11b not started); blocked on open questions 3, 4, which are the client's to answer (PoS system, product↔SKU join). Amended by workstream bluezoo-live-verification: credentials are a per-tenant `{base_url, access_key}` pair, not a lone key |
| 13 | `13` | production-hardening-live-mode | not started | - | - | 2026-07-27 | depends on Phases 11b, 12. Split Tier A (launch gate) / Tier B (governance). Amended by workstream bluezoo-live-verification: secrets hold a `{base_url, access_key}` pair; errors must distinguish *bad credential* / *wrong cluster* / *quota exhausted*; new Tier B item — treat allowance exhaustion as a first-class operational state with client-side metering |
| 14a | `14a` | image-model-upgrade-nano-banana | merged | version_2_model-upgrades | [#14](https://github.com/bluezoo/video-ad-optimization-agent/pull/14) | 2026-07-23 | squash-merged e3c771d (#14); comparison keeps gemini-3-pro-image default; agent default now gemini-3.6-flash |
| 14b | `14b` | video-model-upgrade-omni-flash | merged | version_2_model-upgrades | [#14](https://github.com/bluezoo/video-ad-optimization-agent/pull/14) | 2026-07-23 | squash-merged e3c771d (#14); Veo polling consolidated+tested; Omni NO-GO (previous_interaction_id unsupported), steps 4-6 deferred w/ provenance |
| 15 | `15` | product-onboarding | merged | version_2_product-onboarding | [#13](https://github.com/bluezoo/video-ad-optimization-agent/pull/13) | 2026-07-23 | squash-merged 59cf08c; local-first storage seam, DEMO_DATASET gated seeding, onboarding tools+CLI, Drive bundle + make targets; branch deleted |
| — | `—` | replan-data-track (docs only) | merged | version_2_replan-data-track | [#5](https://github.com/bluezoo/video-ad-optimization-agent/pull/5) | 2026-07-17 | merged a4e0e76 (squash); replan + 1-based renumbering + BlueZoo mimic verification (working-docs/replan-data-track/bluezoo-mapping-verification.md); 11a/11b + Phase 15 rows added above |
| — | `—` | bluezoo-live-verification (script+docs) | merged | version_2_bluezoo-live-verification (deleted) | [#16](https://github.com/bluezoo/video-ad-optimization-agent/pull/16) | 2026-07-27 | merged e834bb9; authenticated schema scan of **two** live tenants; amends pending phases 11b/12/13 only. AP_599 (Apollo, empty) proved structure/entitlements/query mechanics; **MO_92 (Morpheus staging, 5.1M real rows) — owner-approved mid-PR scope extension** — proved semantics (dwell settled, `valid` quantified at a ~4× impressions swing, `campaign_id` resolved), magnitudes, and an undocumented metered bytes-scanned quota. Findings + cost-aware probe + two saved scans (schema/counts only; customer identifiers redacted). Review round corrected the entitlement finding (`group_dwell` documented-but-absent). Demo scenario skipped by design (zero agent-visible change) |
| 16 | `16` | live-api-testing | merged | version_2_live-api-testing | [#15](https://github.com/bluezoo/video-ad-optimization-agent/pull/15) | 2026-07-23 | merged 437fb1c (**merge, not squash** — preserves the 86-commit process record, owner's choice); test-live 26/0 + F1 2/2; Q19 closed; Task 17 deferred (owner follow-up, see Carried work below) |

## Where things stand (2026-07-27)

**Every numbered phase is merged except 11b, 12 and 13** — the three that turn the demo into a connected product. The demo path itself is complete and green.

**The critical path is 11b → 12 → 13, and it is not blocked on engineering.** What holds it up:

| Blocker | Whose call | Notes |
|---|---|---|
| REST vs BigQuery transport (Q1/Q2) | **Client** | A decision, not an unknown — REST is proven end-to-end against real data |
| The `valid` exclusion rule (Q18) | **Client** (partly answerable from data — see below) | Highest-value open question: swings impressions ~4× |
| UTC vs sensor-local day cut (Q18) | **Client** (partly answerable from data) | `time_zone` is sparsely populated across a multi-timezone tenant |
| PoS system + product↔SKU join (Q3/Q4) | **Client** | Gates Phase 12 entirely |

Access and schema are *not* blockers any more: two live tenants, one with 5.1M real rows, full entitlement map, working read-only probe.

## Carried work inside merged phases

Deferred items that a `merged` status hides. None is a regression; each is waiting on something external.

- **Phase 14b steps 4–6** (backend toggle, revision tool, SDK pin) — blocked on Veo Omni supporting `previous_interaction_id` or an equivalent documented revision mechanism, ideally at GA of the interactions surface. NO-GO recorded with provenance; re-evaluate on release, don't re-litigate.
- **Phase 16 Task 17** (demo-asset bundle publish) — owner action: needs the owner's asset source folder for `make demo-assets-build SRC=<folder>` → Drive upload → `DEMO_ASSETS_DRIVE_ID`. Steps documented in `SETUP_INSTRUCTIONS.md`; the code path is tested and skips gracefully when unconfigured.
- **Client outreach from bluezoo-live-verification** — not yet sent. To BlueZoo: the `valid` rule, quota accounting per sensor location, whether the raised ceiling persists, day-cut timezone, `campaign_id` confirmation, per-minute feed status, and a docs bug (their published example query fails against the live API). To the retailer/PoS side: Q3/Q4.
