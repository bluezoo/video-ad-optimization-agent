# Open Questions for BlueZoo

Consolidated questions for BlueZoo/the client, so this can be sent as a single list without digging through 16 files. Purely internal technical questions (e.g. Phase 13's deployment-identity question in `13-production-hardening-live-mode.md`, Phase 10's CMS-delivery-mechanism question in `10-playout-attribution.md`) stay in their own phase docs rather than being surfaced here. Ordered roughly by how much they block downstream work — the first two are the ones most worth resolving soonest.

**Update:** the client's ad-play-tracking email (full text, names redacted, in `.docs/.context/project_context.md`) substantially resolves or narrows questions 4 and 17 below — see each for details. It also confirms the design is an end-of-day batch job (not real-time) and introduces a third external system, the retailer's CMS, whose exact delivery mechanism is still unknown (see Phase 10's open questions). Note: that email references "your list of 5 architectural changes," but the only such list captured across the three reviewed screenshots is a 2-item list (Phase 1/overview's original source) — the fuller 5-item list, if it exists as a separate email, was not among the material reviewed.

## 1. Repo relationship to `github.com/bluezoo/ad-campaign-agent` (blocks Phase 11, shapes Phase 13)

BlueZoo has already publicly announced and open-sourced a project at `github.com/bluezoo/ad-campaign-agent` (press release dated 2026-06-17), naming both the client and this repo's other maintainer, referencing "Gemini Omni" and BigQuery. Is this repo (`video-ad-optimization-agent`) the same effort, a predecessor to it, or a separate/private instance meant to integrate with BlueZoo's public API independently? This directly affects:
- Whether "production launch" (Phase 13) means shipping into that public repo or hardening a separate private deployment.
- Whether the intended live-data integration path is the REST Data Warehouse API (`api.bluezoo.io`, documented and already fetched/verified for this plan) or a BigQuery dataset-share (mentioned in the press release and this repo's own README).

> **Evidence found (workstream replan-data-track, 2026-07-16), half-answering this:** a code-level comparison shows this repo was seeded (mid-June 2026, by the client's account) from a **squashed snapshot of the owner's personal repo** `lavinigam-gcp/ad-campaign-agent` — the trees match closely at that repo's `main`-era state, though no git history was preserved. The owner's repo then continued ~97 unpushed commits (a BQ/services branch: `AudienceProvider` seam, BigQuery-backed synthetic provider, query guard) that never came downstream. So the two lines are the **same effort**, with the personal repo as upstream donor; the plan now treats it as a donor codebase (Phases 5/11a port from it). What still needs the client's confirmation: the intended convergence (does this repo remain the delivery vehicle?) and the transport question below.

## 2. REST API vs. BigQuery for live audience data (blocks Phase 11**b** only — narrowed 2026-07-16)

Directly tied to question 1. BlueZoo's documented REST API (`api.bluezoo.io`) and a BigQuery dataset-share imply meaningfully different adapter code.

> **Narrowed (workstream replan-data-track, 2026-07-16):** per the owner's one-system decision, the demo providers mimic BlueZoo's schema/API behind a single provider seam (Phase 11a — unblocked, ports the donor's proven interface), so this question now blocks **only the live conformer (Phase 11b)**, which is a thin adapter behind the existing seam either way. Two asks for BlueZoo: (a) REST vs. BigQuery dataset-share for live access, and (b) **their actual schema/API reference docs** so the demo-side mimic can be validated rather than inferred (the donor's five-table shape is our working hypothesis). Weak signal on file: the donor repo — the only place anyone built a live-ish path — bet on BigQuery-shaped tables.
>
> **Narrowed again (workstream bluezoo-live-verification, 2026-07-25) — ask (b) is now fully closed; only (a), a decision, remains.** An authenticated scan of a live account (org "Walmart Demo", cluster Apollo / AP_599) completed the drift check this question had been waiting on: 19 tables described, every column and type recorded, `run_query` exercised. Record: `working-docs/bluezoo-live-verification/findings.md`; artifact: `working-docs/bluezoo-live-verification/scan/`. Two of this bullet's own caveats are answered: the **SQL dialect is BigQuery** (confirmed by verbatim BigQuery error text, no longer inference), and the "three coexisting hostnames with no canonical one" premise was **wrong** — hostnames are cluster-scoped, so there is no canonical one to name (see Q18). **REST is proven working end-to-end**, which reframes (a): it is now a client *preference* between a working REST path and a hypothetical BigQuery share, not an unknown capability.
>
> **Narrowed further (same workstream, later on 2026-07-16):** ask (b) is now substantially satisfied — the mimic **was validated** field-by-field against BlueZoo's live *published* API docs (`api.bluezoo.io`, full record in `working-docs/replan-data-track/bluezoo-mapping-verification.md`): the donor's structure is real (14-table inventory, 106 dwell bins, grain, exact `sensor_visits` columns), with five port-time corrections folded into Phase 5/10. What remains of (b): an **authenticated** `desc_table`/`run_query` round-trip to catch published-docs-vs-live drift (needs an AccessKey — see Q12), plus (a) unchanged, plus the batched semantics confirmations now in Q18. Note the published docs never name the `run_query` SQL dialect (BigQuery is inference from type names) and list three coexisting API hostnames with no canonical one — both now explicit asks.

## 3. Revenue/PoS integration target (blocks Phase 12 entirely)

Which point-of-sale or e-commerce system should the first real revenue integration target (Square, Shopify, a specific pilot customer's system, or a generic webhook/CSV ingestion path)? Unlike audience data, there's no single documented API to default to here.

## 4. Sale-to-exposure attribution methodology (blocks Phase 12's core value, not just its plumbing)

**Substantially resolved by the client's ad-play-tracking email** (see `.docs/.context/project_context.md`): the client's `AdPlayRecord` schema specifies attribution by product identifier + time window, looked up directly against the retailer's PoS system — not time-window proximity, beacon correlation, or self-reported codes. What remains open is narrower: can the specific PoS system chosen in question 3 actually resolve sales by product identifier, or does the first live demo need the coarser store-day fallback (Phase 12, step 3)?

## 5. `circulation` metric definition (Phase 3 glossary — does not block Phase 3 itself)

This app's `video_metrics.circulation` column has a candidate mapping (broader foot-traffic/opportunity-to-see, possibly BlueZoo's `sensor_visitors` occupancy or an outer-zone visit count, as distinct from `impressions` = inner-zone `sensor_visits`) — but this is **not confirmed** against BlueZoo's docs or the client's own usage. Phase 3's glossary handles this by writing the definition down as "app-local synthetic, BlueZoo mapping unresolved" rather than waiting on this answer — so this question doesn't block Phase 3, only the eventual real-data alignment in Phase 11.

## 6. Unique-reach metric (Phase 3 glossary)

Does BlueZoo's `group_uv_*` (unique visitor) concept need to be surfaced as a distinct metric in this app, separate from raw impressions, or is impressions-only sufficient for the RPI use case the client cares about?

> **Refined (workstream replan-data-track, 2026-07-16, from the live-docs verification):** two facts to carry into whichever answer: (a) daily unique-visitor counts are **non-additive** — summing `group_uv_daily` across days does not give weekly/monthly reach (that's why BlueZoo ships the separate weekly/monthly/custom rollup tables, which the donor mimic cut); the port documents "never sum daily UV for reach." (b) Live per-ad-campaign UV presupposes BlueZoo-side **group** configuration mirroring each campaign's store set (UV tables are `group_id`-keyed, with no campaign column, contrary to the donor spec's claim) — adjacent to Q11's mapping question.
>
> **CORRECTED (workstream bluezoo-live-verification, 2026-07-25) — refinement (b)'s parenthetical was wrong, and we had it backwards.** Against the live schema, `group_uv_daily` carries **`campaign_id` AND `campaign_name`** (24 columns in total, also including `cuv`, `calculation_unique_visitor_count`, `target_uv`, `actual_accuracy`, `total_cost`). The donor spec's claim that BlueZoo stamps campaign on `group_uv_*` was **right**; the 2026-07-16 docs-based correction of it was wrong — the published docs were simply incomplete. Recorded openly rather than silently edited, because ws05 port correction #2 (`bluezoo-mapping-verification.md`, item 2) told the port to "correct that prose," and anyone reading that instruction should see it has since been overturned.
>
> Two things survive the reversal. First, the `campaign_id` → **`ad_campaign_id`** rename is *reinforced*, not weakened: a bare `campaign_id` now collides on `group_uv_*` too, not only on the flow tables — and `group_convert`'s live schema (`campaign_id`, `group_source_id`, `group_destination_id`) independently confirms the flow-campaign meaning. Second, refinement (b)'s *substance* — that per-ad-campaign UV needs BlueZoo-side group configuration — is unverified either way: the column exists, but with zero rows on this account we cannot see whether it is populated, nor whose campaign concept it holds. Ask BlueZoo what `group_uv_daily.campaign_id` refers to before designing against it. Full record: `working-docs/bluezoo-live-verification/findings.md` (Part 2 #6).

## 7. Non-fashion proof vertical (Phase 8)

Which non-fashion vertical should the generalization work's proof-of-concept fixture catalog use? BlueZoo's own marketed verticals are out-of-home advertising, retail, hospitality, and smart cities — picking one that matches an actual upcoming conversation/demo would make Phase 8's fixture data doubly useful.

> **Answered (workstream 08, 2026-07-20):** broader than any single vertical —
> the owner wants the schema to serve *any retail vertical sellable on BlueZoo
> in-store screens*. The proof fixture is a multi-vertical **retail core test
> set** (`app/database/retail_products_data.py`: beverage, QSR menu item,
> consumer electronics, furniture, home appliance), attributes-first. Product
> images are referenced but not generated here — users will either upload
> photos or generate them via nano banana (Phase 14a model, Phase 15 tools),
> growing this core set into the standard test imagery.

## 8. Product CRUD scope (Phase 8) — ANSWERED 2026-07-16

~~Is a full product-CRUD tool actually needed now, or is seeded-fixture-only sufficient for near-term demos?~~ **Answered by the owner: yes, it's needed.** From-scratch onboarding (fresh product images → products → campaigns → analytics, no preseeded catalog) is a stated goal; product CRUD (agent tools + CLI wrapper) is now Phase 15, `15-product-onboarding.md`. No client input required.

> **Amended (workstream 15, 2026-07-22):** implemented — `create_product` / `import_products_from_folder` / `generate_product_image` on the Campaign agent, plus the CLI twin `scripts/onboard_products.py` (creation-side only; update/delete tools remain unbuilt by design).

## 9. RPI demo range realism (Phase 5)

The two existing (soon-to-be-unified) mock generators use different RPI ranges ($0.02-$0.08 vs. $0.08-$0.15) — which looks more credible for demo purposes in front of the client/prospects?

## 10. Demo screen count (Phase 10)

How many screens should the synthetic playout/attribution demo simulate — does the client have a preferred number/layout matching a specific prospect walkthrough?

## 11. Screen-to-BlueZoo-sensor mapping convention (Phase 11)

Is there an existing convention from BlueZoo's own dashboard/API for mapping physical screens to sensor/zone IDs, or does this app need to invent its own mapping table?

> **Refined (workstream replan-data-track, 2026-07-16, from the live-docs verification):** the mapping question extends one level up — unique-visitor data is keyed by BlueZoo-side **groups** (`group_id`), so if per-ad-campaign unique reach is wanted (Q6), BlueZoo group configuration must mirror each campaign's store/sensor set, on their side. Ask how groups are administered alongside the sensor-ID convention.
>
> **ANSWERED (workstream bluezoo-live-verification, 2026-07-25) — BlueZoo has a mapping convention and it is API-discoverable; we do not invent one.** The live scan found **`group_sensor_history`** (`group_id`, `group_name`, `sensor_id`, `sensor_name`, `timestamp`) — the group↔sensor mapping table, absent from the published 14-table docs. Because it is timestamped, **group membership changes over time**: a mapping read is as-of-a-date, not a static lookup, and any cached mapping is a snapshot. Phase 11 step 5's "does this app need to invent one?" is settled: no. Two parts stay open — (i) whether the retailer's CMS emits BlueZoo's native sensor ID or this app's screen ID (a *client* question, not a BlueZoo one; unchanged), and (ii) how groups are *administered* on BlueZoo's side, which the table shows but doesn't explain. Caveat: zero rows on this account, so the table's shape is proven and its contents are not.

## 12. BlueZoo sandbox access (Phase 11)

Does BlueZoo provide a sandbox/test account for adapter development, or does this require a real production AccessKey against live sensor hardware?

> **Partly answered, and it moved the problem (workstream bluezoo-live-verification, 2026-07-25).** The owner obtained a real account — org "Walmart Demo", cluster/account Apollo / AP_599, Super Admin — and it authenticates and answers queries fine. So *access* is no longer the blocker. **Data is.** Every one of the 19 entitled tables returns zero rows across a 2020–2030 window: a fresh tenant with no deployed sensors. That is enough to verify structure, entitlements, query mechanics, error semantics and auth — and not enough to verify a single value. Phase 11b's `CachedBlueZooAudienceDataSource`, whose entire purpose is proving real and synthetic payloads are interchangeable, **cannot be built from this account.**
>
> **This is now the highest-priority BlueZoo ask:** give us a tenant with real historical data, or seed AP_599. Everything value-level in Q18 stays blocked behind it.

## 13. Message-content tracing / data governance (Phase 13)

Does BlueZoo or legal have a specific requirement around OTel message-content capture in traces, once real customer/store data flows through prompts in connected mode? This should drive the enforcement decision in Phase 13 rather than the plan guessing at a default.

## 14. Image resolution requirements (Phase 14a)

Is Nano Banana 2 Lite's 1K resolution cap acceptable for this app's actual display/demo surfaces, or does a specific use case need the current higher-resolution default?

> **Amended (workstream 16, 2026-07-23):** corroborating live-pipeline
> evidence, recorded opportunistically during Task 12/13's real end-to-end
> runs (not synthetic benchmark calls like Phase 14a's) —
> `.docs/version2-plan/working-docs/16-live-api-testing/calibration/media-metadata.json`:
> both the wearable (blue-floral-maxi-dress) and non-wearable
> (aurora-cold-brew-330ml) scene-image pipelines produced **768x1376 PNG,
> ~1.4MB**, matching Phase 14a's 1K-tier benchmark finding exactly (same
> `gemini-3-pro-image` default). No new resolution requirement surfaced from
> real usage; still open in the sense that no owner has explicitly ratified
> "1K is acceptable" as a final answer, but two independent measurements (a
> synthetic benchmark and now a live product/demo pipeline) now agree.

## 15. Video backend default, post-evaluation (Phase 14b) — ANSWERED for now 2026-07-23

> **Amended (workstream 14, 2026-07-23):** answered by a real prototype (not
> docs alone): wait. `previous_interaction_id` — the capability that would
> justify an omni_flash backend + revision tool — is explicitly unsupported
> server-side for gemini-omni-flash-preview, and the interactions surface is
> mid-migration (get 500s on sync ids; turn_list->step_list). Veo 3.1 stays
> the only video backend. Revisit condition + banked working request shapes:
> `working-docs/14-model-upgrades/omni-prototype-findings.md`. Q15's second
> half (should Omni ever become *default*) stays open for that revisit; note
> Omni's 4s/24fps/720p ceiling vs Veo argues for Veo-as-default regardless.

> **Amended (workstream 16, 2026-07-23):** live-pipeline duration/resolution
> evidence for Veo 3.1 (the standing default), recorded from Task 12's real
> end-to-end runs —
> `.docs/version2-plan/working-docs/16-live-api-testing/calibration/media-metadata.json`:
> both wearable and non-wearable pipelines produced **720x1280 @ 24fps,
> 4.01s actual duration for a requested 4s** (96 frames). 6s/8s requested
> durations remain unmeasured (only the 4s case was exercised live this
> workstream). This is video-output evidence, not a backend-choice
> reconsideration — Q15's Veo-vs-Omni decision above is unaffected.

**Corrected framing after Codex review:** the Interactions API and Omni Flash model are both currently labeled experimental/preview by Google's own primary sources — not GA, as an earlier draft of this plan assumed. Given that, is it worth investing engineering time in this integration now, or should Phase 14b wait for either surface to reach GA? If pursued now, once (if) it reaches GA, should it become the *default* video backend, or does this app's specific demo needs (duration/resolution constraints) argue for keeping Veo as default regardless?

## 16. Is "zero external accounts for demo mode" actually a requirement? (Phase 6/philosophy) — RESOLVED 2026-07-16

~~Is "no BlueZoo/PoS credentials required" the actual bar, or does "zero external accounts" need to be taken literally?~~ **Resolved by the owner: local-first.** The bar is: GCP credentials are needed **only for model calls** (Gemini/Veo/image generation); product images and generated videos save/load locally with no GCS bucket required, and GCS becomes an explicit opt-in for cloud deploys. The local storage backend (and removal of the personal-bucket default at `app/config.py:52-53`, which `app/storage.py:189/208/224` currently hard-depend on) is Phase 15, `15-product-onboarding.md`, step 1. No client input required.

> **Amended (workstream 15, 2026-07-22):** implemented — the personal-bucket default is deleted (`GCS_BUCKET` unset ⇒ local mode; the cited `config.py:52-53` lines no longer exist), product images gained a full local path under `product-images/`, all four URL-emitting tools are existence-checked and emit no `storage.googleapis.com` URLs locally, and demo assets ship via the Drive-bundle scripts (`scripts/demo_assets.py`).

## 17. Sub-15-minute per-ad-play windows: which fallback does BlueZoo support? (Phase 11b; shapes Phase 7's credibility once real data lands)

**Narrowed by the client's ad-play-tracking email, then answered-in-the-negative by the live docs (2026-07-16).** The client's design calls BlueZoo's API per `AdPlayRecord`'s own start/end window directly — so no proportional-allocation formula is needed *if* BlueZoo can answer arbitrary windows. The docs-verification (see `working-docs/replan-data-track/bluezoo-mapping-verification.md`) established it **cannot, on any documented endpoint**: the Data Warehouse is quarter-hour resolution; Real-time `get_visits` returns only the last 8 *full* 15-minute slots; `get_occupancy_count` is momentary; the opt-in `sensor_visitors_per_minute` table is *occupancy*, not visits. The question for BlueZoo is therefore no longer "does it work?" but **"which fallback do you support for ad plays shorter than 15 minutes?"**: (a) we apportion 15-minute slots across overlapping plays, (b) you enable the per-minute occupancy table as a proxy, or (c) an undocumented capability exists (raw event access, or finer grain via the Q2 BigQuery dataset-share). Does not block Phase 10's demo join (the generator emits whatever grain the join needs); blocks only the live per-ad-play accuracy story in Phase 11b.

> **Fallback (b) is available on our tenant (workstream bluezoo-live-verification, 2026-07-25).** `sensor_visitors_per_minute` **is entitled** on Apollo / AP_599 — no BlueZoo request needed to try it here. Its live columns are `visitors_inner` / `visitors_outer`, confirming the docs-verification's read that it is **occupancy, not visits**; using it as an impressions proxy remains an approximation with different semantics, not a like-for-like substitute. Two parts of this question survive: whether the table is generally available to *other* customers or opt-in per account (a real BlueZoo question, and the reason Phase 11b must detect entitlements via `list_tables` rather than assume them), and whether (c) — an undocumented raw-event or finer-grain path — exists at all. And with zero rows on the account, "available" means the table can be queried, not that its accuracy as a proxy has been tested against anything.

## 18. Batched schema-semantics confirmations from the 2026-07-16 docs verification (Phase 11b checklist — none block anything else)

Small confirmations the published docs can't settle, best asked as one batch alongside Q2 (full context in `working-docs/replan-data-track/bluezoo-mapping-verification.md`):

- Which API hostname is canonical — the docs use `hermes.apollo.bluezoo.io`, `apollo-api.bluefoxengage.com`, and `morpheus-api.bluefoxengage.com` interchangeably.
- `run_query` SQL dialect (BigQuery is our inference from the INT64/FLOAT64 type names — never stated), row caps, and rate limits.
- Are daily buckets (`group_uv_daily` etc.) cut on UTC days or sensor-local days (`time_offset`)? Our mimic documents UTC.
- Should `valid=false` rows be excluded when aggregating impressions? (`valid` appears in examples, undescribed.)
- Are `sensor_dwell` distribution bin values 0–1 shares or 0–100 percentages? (Docs say "percentage" with no numeric example; affects the cached-real conformer's normalization.)
- `group_convert` / `group_dwell` schemas (both exist in `list_tables` with zero documentation), and `sensor_dwell.distribution_weight` semantics.

> **Halved by the live scan (workstream bluezoo-live-verification, 2026-07-25).** Everything answerable from schema alone is answered; what's left needs *rows*. Record: `working-docs/bluezoo-live-verification/findings.md`.
>
> **Answered — drop from the ask:**
> - *Canonical hostname* — **the question's premise was wrong.** Hostnames are cluster-scoped, not variants of one canonical host: `hermes.apollo.bluezoo.io` and `apollo-api.bluefoxengage.com` are aliases for the Apollo cluster (identical 200s); `morpheus-api.bluefoxengage.com` returns `BAD_TOKEN` for the same key because it is a different cluster. The dashboard Profile screen names the customer's cluster. Nothing to ask; the adapter takes the base URL as tenant config.
> - *SQL dialect* — **BigQuery**, confirmed by verbatim BigQuery error text, not inferred.
> - *`group_convert` schema* — now recorded in the scan artifact (`campaign_id`, `group_source_id`, `group_destination_id`, `date_start`, …), which independently confirms BlueZoo's flow-campaign meaning of `campaign_id`. **`group_dwell` remains unanswered for the opposite reason: it is not entitled on this account at all.** That absence is itself the sharper finding — a *documented* table missing while six undocumented ones are present proves entitlements are not a superset of the docs, which is why Phase 11b must probe `list_tables` rather than assume any table exists.
>
> **New, and undocumented — worth telling BlueZoo we found it:** every `run_query` must constrain `date_start`, `date_end` or `timestamp` in its WHERE clause, enforced server-side. Their own published example (`select * from sensor_visitors limit 1`) fails against the live API. Worth flagging to them as a docs bug, and non-negotiable for our query builder.
>
> **Still open — all blocked on the zero-rows problem (Q12), not on schema:** dwell bin scale (0–1 vs 0–100) and `distribution_weight` semantics; whether `valid=false` rows should be excluded from impressions; UTC vs sensor-local day cutting — noting the live schema carries an undocumented **`time_zone` (STRING)** column on every sensor table alongside `time_offset`, so ask what the two mean together; and `run_query` row caps / rate limits.

## 19. Integration eval suite: vacuous under pytest, and eval sets fail when genuinely run (discovered workstream 09, 2026-07-22) — RESOLVED 2026-07-22, DELIVERED workstream 16, 2026-07-23

**Resolved by the owner (2026-07-22, ws09 manual-testing feedback): full live repair — option (a), expanded.** "We should have both fast test and full test with live api and both should pass. dont worry about the cost." Scoped as new Phase 16 (`16-live-api-testing.md`): real-env integration fixture + vacuity guard, eval-set trajectory repair, default model → `gemini-3.6-flash`, live Veo/image-gen tests, and a Gemini-judge script reviewing generated media. `make test` stays fast-by-default; the live tier gets its own target. Original problem statement kept below for the record.

> **Amended (workstream 16, 2026-07-23): delivered, mechanism refined.**
> Repair option (a) shipped in full — `tests/integration/eval_harness.py` +
> `tests/live/` (5 eval sets repaired, live media/judge tests, `make
> test-live`, 26 passed/0 failed at completion). One correction to problem
> statement 1 below, found while building the fix: `ADK`'s `LocalEvalService`
> was never the culprit — it correctly records per-case
> `InferenceStatus.FAILURE`/`final_eval_status=FAILED` when inference fails.
> The vacuity was entirely in `AgentEvaluator.evaluate_eval_set`'s pytest
> aggregation, which compares only *mean metric scores* and never inspects
> `final_eval_status` — with every inference 403ing under the fake
> `test-project`, there were no metric scores to average, so the assert
> passed on zero real calls. The harness fixes this by asserting per-case
> `final_eval_status` directly (`assert_eval_outcomes`), not by capturing a
> logger as the phase doc originally sketched — see `16-live-api-testing.md`
> step 1's amendment and `CLAUDE.md`'s Gotchas section for the full record.
> `make test` no longer runs `tests/integration` at all (moved to the new
> `make test-live`, which also includes `tests/live`).

Two stacked pre-existing problems, mechanism fully pinned in workstream 09's WORK_LOG (2026-07-22 DISCOVERY entry):

1. **Under pytest the suite never calls the LLM.** `tests/conftest.py`'s autouse fixture sets `GOOGLE_CLOUD_PROJECT=test-project`; every inference 403s; ADK's `LocalEvalService` swallows per-case inference exceptions; `AgentEvaluator.evaluate_eval_set` derives failures only from metric results (empty when inference failed) — so all five eval sets "pass" in ~5s with zero evaluation. Every historical "integration passed" result in this repo was vacuous.
2. **When genuinely executed** (standalone `asyncio.run(AgentEvaluator.evaluate(...))` with real env), the eval sets FAIL as authored: expected trajectories pin direct tool calls, but the coordinator's real trajectory wraps them in `transfer_to_agent`, and `response_match_score` ≈ 0 against the pinned reference responses.

**Repair options (owner decision):** (a) full fix — a `tests/integration/conftest.py` fixture that restores real env per integration test, a vacuity guard (fail/xfail when ADK logs swallowed inference failures), and rewriting all five eval sets' expected trajectories (+ a `test_config.json` criteria file) against the live agent; note this makes `make test` (the default target) spend real LLM calls and minutes per run, so it likely also means moving integration out of the default target. (b) Defer: keep the suite as-is, documented as vacuous (CLAUDE.md Gotcha), and rely on demo-scenario verification (which does drive the live agent end-to-end) as the behavioral gate until a dedicated test-infra slot. Workstream 09 shipped its Task 7 eval cases correctly authored but documented as unexercised, per (b) pending the decision.

---

None of these block starting the plan — Phase 1 through Phase 10, Phase 11a, and Phase 15 can all proceed without any of them being answered. Question 17 is now a "which fallback?" ask for BlueZoo (the docs confirmed no endpoint serves sub-15-minute visit windows) and does not block Phase 10's demo join, which uses the deterministic generator. Questions 1 and 2 block **Phase 11b only** (the live conformer — 11a, the seam port, is unblocked; Q2's mimic-validation half is already satisfied against the published docs, leaving the transport decision and an authenticated drift-check); question 18 is a batch of small 11b checklist confirmations; question 3 blocks Phase 12; question 4 is now a narrower capability check against the PoS system chosen in question 3. Questions 7, 8 and 16 are answered/resolved (owner decisions, 2026-07-16 and 2026-07-20). Question 11 (screen-to-sensor mapping) and question 12 (sandbox access) inform Phase 11b but don't block starting it. The rest are refinements that improve later phases but don't block starting them.

> **Amended (workstream bluezoo-live-verification, 2026-07-25).** A live account (Apollo / AP_599) has changed which of the above are still questions. **Answered from the live schema:** Q11 (`group_sensor_history` is BlueZoo's mapping table), Q17's fallback-(b) availability, and most of Q18 (dialect, hostname premise, `group_convert` schema). **Q12 is answered but inverted** — access is granted; the account has **zero rows**, so no value-level question can be settled and Phase 11b's `CachedBlueZooAudienceDataSource` cannot be built at all. That makes **"give us a tenant with real data, or seed AP_599" the single highest-priority ask** — Q18's remaining bullets and Q6's campaign-column semantics all sit behind it. Q1 and Q2 are unchanged in status but changed in character: REST is now *proven working*, so what's left is the client's transport decision, not a capability unknown.
