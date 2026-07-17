# Open Questions for BlueZoo

Consolidated questions for BlueZoo/the client, so this can be sent as a single list without digging through 16 files. Purely internal technical questions (e.g. Phase 12's deployment-identity question in `13-production-hardening-live-mode.md`, Phase 9's CMS-delivery-mechanism question in `10-playout-attribution.md`) stay in their own phase docs rather than being surfaced here. Ordered roughly by how much they block downstream work — the first two are the ones most worth resolving soonest.

**Update:** the client's ad-play-tracking email (full text, names redacted, in `.docs/.context/project_context.md`) substantially resolves or narrows questions 4 and 17 below — see each for details. It also confirms the design is an end-of-day batch job (not real-time) and introduces a third external system, the retailer's CMS, whose exact delivery mechanism is still unknown (see Phase 9's open questions). Note: that email references "your list of 5 architectural changes," but the only such list captured across the three reviewed screenshots is a 2-item list (Phase 0/overview's original source) — the fuller 5-item list, if it exists as a separate email, was not among the material reviewed.

## 1. Repo relationship to `github.com/bluezoo/ad-campaign-agent` (blocks Phase 10, shapes Phase 12)

BlueZoo has already publicly announced and open-sourced a project at `github.com/bluezoo/ad-campaign-agent` (press release dated 2026-06-17), naming both the client and this repo's other maintainer, referencing "Gemini Omni" and BigQuery. Is this repo (`video-ad-optimization-agent`) the same effort, a predecessor to it, or a separate/private instance meant to integrate with BlueZoo's public API independently? This directly affects:
- Whether "production launch" (Phase 12) means shipping into that public repo or hardening a separate private deployment.
- Whether the intended live-data integration path is the REST Data Warehouse API (`api.bluezoo.io`, documented and already fetched/verified for this plan) or a BigQuery dataset-share (mentioned in the press release and this repo's own README).

> **Evidence found (workstream replan-data-track, 2026-07-16), half-answering this:** a code-level comparison shows this repo was seeded (mid-June 2026, by the client's account) from a **squashed snapshot of the owner's personal repo** `lavinigam-gcp/ad-campaign-agent` — the trees match closely at that repo's `main`-era state, though no git history was preserved. The owner's repo then continued ~97 unpushed commits (a BQ/services branch: `AudienceProvider` seam, BigQuery-backed synthetic provider, query guard) that never came downstream. So the two lines are the **same effort**, with the personal repo as upstream donor; the plan now treats it as a donor codebase (Phases 4/10a port from it). What still needs the client's confirmation: the intended convergence (does this repo remain the delivery vehicle?) and the transport question below.

## 2. REST API vs. BigQuery for live audience data (blocks Phase 10**b** only — narrowed 2026-07-16)

Directly tied to question 1. BlueZoo's documented REST API (`api.bluezoo.io`) and a BigQuery dataset-share imply meaningfully different adapter code.

> **Narrowed (workstream replan-data-track, 2026-07-16):** per the owner's one-system decision, the demo providers mimic BlueZoo's schema/API behind a single provider seam (Phase 10a — unblocked, ports the donor's proven interface), so this question now blocks **only the live conformer (Phase 10b)**, which is a thin adapter behind the existing seam either way. Two asks for BlueZoo: (a) REST vs. BigQuery dataset-share for live access, and (b) **their actual schema/API reference docs** so the demo-side mimic can be validated rather than inferred (the donor's five-table shape is our working hypothesis). Weak signal on file: the donor repo — the only place anyone built a live-ish path — bet on BigQuery-shaped tables.

## 3. Revenue/PoS integration target (blocks Phase 11 entirely)

Which point-of-sale or e-commerce system should the first real revenue integration target (Square, Shopify, a specific pilot customer's system, or a generic webhook/CSV ingestion path)? Unlike audience data, there's no single documented API to default to here.

## 4. Sale-to-exposure attribution methodology (blocks Phase 11's core value, not just its plumbing)

**Substantially resolved by the client's ad-play-tracking email** (see `.docs/.context/project_context.md`): the client's `AdPlayRecord` schema specifies attribution by product identifier + time window, looked up directly against the retailer's PoS system — not time-window proximity, beacon correlation, or self-reported codes. What remains open is narrower: can the specific PoS system chosen in question 3 actually resolve sales by product identifier, or does the first live demo need the coarser store-day fallback (Phase 11, step 3)?

## 5. `circulation` metric definition (Phase 2 glossary — does not block Phase 2 itself)

This app's `video_metrics.circulation` column has a candidate mapping (broader foot-traffic/opportunity-to-see, possibly BlueZoo's `sensor_visitors` occupancy or an outer-zone visit count, as distinct from `impressions` = inner-zone `sensor_visits`) — but this is **not confirmed** against BlueZoo's docs or the client's own usage. Phase 2's glossary handles this by writing the definition down as "app-local synthetic, BlueZoo mapping unresolved" rather than waiting on this answer — so this question doesn't block Phase 2, only the eventual real-data alignment in Phase 10.

## 6. Unique-reach metric (Phase 2 glossary)

Does BlueZoo's `group_uv_*` (unique visitor) concept need to be surfaced as a distinct metric in this app, separate from raw impressions, or is impressions-only sufficient for the RPI use case the client cares about?

## 7. Non-fashion proof vertical (Phase 7)

Which non-fashion vertical should the generalization work's proof-of-concept fixture catalog use? BlueZoo's own marketed verticals are out-of-home advertising, retail, hospitality, and smart cities — picking one that matches an actual upcoming conversation/demo would make Phase 7's fixture data doubly useful.

## 8. Product CRUD scope (Phase 7) — ANSWERED 2026-07-16

~~Is a full product-CRUD tool actually needed now, or is seeded-fixture-only sufficient for near-term demos?~~ **Answered by the owner: yes, it's needed.** From-scratch onboarding (fresh product images → products → campaigns → analytics, no preseeded catalog) is a stated goal; product CRUD (agent tools + CLI wrapper) is now Phase 14, `15-product-onboarding.md`. No client input required.

## 9. RPI demo range realism (Phase 4)

The two existing (soon-to-be-unified) mock generators use different RPI ranges ($0.02-$0.08 vs. $0.08-$0.15) — which looks more credible for demo purposes in front of the client/prospects?

## 10. Demo screen count (Phase 9)

How many screens should the synthetic playout/attribution demo simulate — does the client have a preferred number/layout matching a specific prospect walkthrough?

## 11. Screen-to-BlueZoo-sensor mapping convention (Phase 10)

Is there an existing convention from BlueZoo's own dashboard/API for mapping physical screens to sensor/zone IDs, or does this app need to invent its own mapping table?

## 12. BlueZoo sandbox access (Phase 10)

Does BlueZoo provide a sandbox/test account for adapter development, or does this require a real production AccessKey against live sensor hardware?

## 13. Message-content tracing / data governance (Phase 12)

Does BlueZoo or legal have a specific requirement around OTel message-content capture in traces, once real customer/store data flows through prompts in connected mode? This should drive the enforcement decision in Phase 12 rather than the plan guessing at a default.

## 14. Image resolution requirements (Phase 13a)

Is Nano Banana 2 Lite's 1K resolution cap acceptable for this app's actual display/demo surfaces, or does a specific use case need the current higher-resolution default?

## 15. Video backend default, post-evaluation (Phase 13b)

**Corrected framing after Codex review:** the Interactions API and Omni Flash model are both currently labeled experimental/preview by Google's own primary sources — not GA, as an earlier draft of this plan assumed. Given that, is it worth investing engineering time in this integration now, or should Phase 13b wait for either surface to reach GA? If pursued now, once (if) it reaches GA, should it become the *default* video backend, or does this app's specific demo needs (duration/resolution constraints) argue for keeping Veo as default regardless?

## 16. Is "zero external accounts for demo mode" actually a requirement? (Phase 5/philosophy) — RESOLVED 2026-07-16

~~Is "no BlueZoo/PoS credentials required" the actual bar, or does "zero external accounts" need to be taken literally?~~ **Resolved by the owner: local-first.** The bar is: GCP credentials are needed **only for model calls** (Gemini/Veo/image generation); product images and generated videos save/load locally with no GCS bucket required, and GCS becomes an explicit opt-in for cloud deploys. The local storage backend (and removal of the personal-bucket default at `app/config.py:52-53`, which `app/storage.py:189/208/224` currently hard-depend on) is Phase 14, `15-product-onboarding.md`, step 1. No client input required.

## 17. Cross-creative attribution rule when multiple videos share one BlueZoo sensor window (narrowed: Phase 10 technical check — does BlueZoo answer sub-15-minute windows accurately; shapes Phase 6's credibility once real data lands)

**Narrowed, not eliminated, by the client's ad-play-tracking email** (see `.docs/.context/project_context.md`): the client's design calls BlueZoo's API per `AdPlayRecord`'s own start/end window directly, rather than pre-aggregating a shared 15-minute bucket and splitting it after the fact — so this is no longer a fundamental attribution-methodology question needing a proportional-allocation formula. What's still open is a narrower, technical question (tracked in Phase 9/10): does BlueZoo's API actually return accurate, non-duplicated counts for a query window shorter than its confirmed 15-minute historical grain — likely meaning the Real-time API (`get_occupancy_count`/`get_visits`) needs to be used for per-ad-play queries, rather than the Data Warehouse `run_query` path. This needs a direct technical check against BlueZoo's API (Phase 10), not a design decision.

---

None of these block starting the plan — Phase 0 through Phase 9, Phase 10a, and Phase 14 can all proceed without any of them being answered. Question 17 is a Phase 10b verification item (does BlueZoo answer sub-15-minute windows accurately) and does not block Phase 9's demo join, which uses the deterministic generator. Questions 1 and 2 block **Phase 10b only** (the live conformer — 10a, the seam port, is unblocked); question 3 blocks Phase 11; question 4 is now a narrower capability check against the PoS system chosen in question 3. Questions 8 and 16 are answered/resolved (owner decisions, 2026-07-16). Question 11 (screen-to-sensor mapping) and question 12 (sandbox access) inform Phase 10b but don't block starting it. The rest are refinements that improve later phases but don't block starting them.
