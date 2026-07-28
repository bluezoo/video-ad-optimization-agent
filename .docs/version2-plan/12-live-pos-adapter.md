# Phase 12 — Live Revenue / PoS Adapter

## Goal

Build a real `RevenueDataSource` so RPI's numerator (revenue) can come from an actual point-of-sale or attribution system, the same way Phase 11 makes the denominator (impressions) real. Today, revenue is 100% synthetic (`app/database/mock_data.py`), and there is no PoS/revenue integration of any kind, confirmed via repo-wide grep.

## Update: the client's ad-play-tracking design (see Phase 10) specifies the attribution key — per product identifier, not per-store-day

Per the client's email (full text in `.docs/.context/project_context.md`), each `AdPlayRecord` carries its own `product_id`, and the end-of-day reconciliation job looks up revenue for that ad-play by product identifier + time window against the retailer's PoS data warehouse. This resolves what was previously an open attribution-methodology question in this plan's first draft: **per-product-identifier revenue lookup is the specified design, not an aspirational stretch goal beyond a coarser store-day fallback.** Step 3 below is updated accordingly — the store-day milestone is now a fallback to reach for only if the chosen PoS system genuinely can't support product-level lookups, not the default recommended first target.

## This phase is more open-ended than Phase 11 — read the open questions first

Unlike BlueZoo's audience data (one well-documented API this plan has already fetched and verified), there is no equivalent "the revenue source" — it depends entirely on which point-of-sale or e-commerce system an actual BlueZoo customer uses, and whether that system exposes sales by product identifier (the client's design assumes it does — this needs confirming against whichever PoS system is chosen, not treated as guaranteed for every retailer). This is still partly a **business/integration question** (which PoS system, what access), even though the attribution methodology itself is now specified.

## Current state

- `revenue` in `video_metrics` (`app/database/db.py:139-151`) is entirely synthetic (`_generate_mock_video_metrics()`, being unified in Phase 5).
- No PoS, e-commerce, or payments integration exists anywhere in the codebase.
- BlueZoo's own API does not provide revenue data — it's an audience/attention measurement platform (confirmed via Phase 3's research), so this is necessarily a separate integration, not something bundled with Phase 11.

## Steps

1. **Resolve with the client which PoS/revenue system to target first** — this determines everything else in this phase (Square, Shopify, a generic CSV/webhook ingestion path, or something specific to a BlueZoo pilot customer). Do not start building against a specific vendor's API without this confirmed. As part of this, confirm the chosen system can look up sales **by product identifier** — the client's `AdPlayRecord` design (Phase 10) assumes this is possible; if the first target system can't do it, that's a real gap to flag back to the client, not something to quietly work around.
2. Once a target is chosen, define a `RevenueInterval` DTO and a `RevenueDataSource` interface analogous to Phase 11's `AudienceDataSource`. **Correction from review: a bare `get_revenue(id, start, end) -> float` is too small to align real PoS data reliably** — it omits currency, gross-vs-net/refund/tax handling, store/SKU identifiers, event timezone, and source transaction identity, all of which the current schema also lacks (`video_metrics.revenue` is a single undifferentiated `REAL` column, `app/database/db.py:146`). Define the DTO with at least: amount, currency, gross/net/refund basis (explicitly, not assumed), store/SKU key(s) (this is where `product_id` from Phase 10's `AdPlayRecord` plugs in directly), a UTC timestamp or interval, and a source transaction ID for idempotency — even if the first real adapter only populates a subset of these, the interface should not preclude them.
3. **Build the real adapter to look up revenue per product identifier + time window, matching the client's `AdPlayRecord` design (Phase 10) — this is the specified target, not an aspirational one.** Fall back to a coarser store × day (or store × 15-minute bucket, matching Phase 10/11's grain) milestone only if the chosen PoS system genuinely cannot resolve sales by product identifier — and if that fallback is needed, get the client's explicit sign-off that a coarser, clearly-labeled **observational** (not causal) store-day number is an acceptable substitute before shipping it as the first live integration.
4. Implement `DemoRevenueDataSource` (wraps Phase 5's deterministic synthetic revenue, unchanged) and the real adapter for whichever system is chosen, both behind the same interface, wired to `APP_MODE` exactly as Phase 11 wires `AudienceDataSource`.
5. **Minimum live-secret handling belongs in this phase, not deferred to Phase 13** — same correction as Phase 11, step 6: read PoS credentials from a real secret store from the start, not a plaintext `.env` file migrated later.

## Validation

- [ ] `DemoRevenueDataSource` and the real adapter both pass a shared contract test suite (same pattern as Phase 11).
- [ ] With `APP_MODE=connected`, revenue data flows into `compute_rpi()` (Phase 4) correctly, joined against Phase 11's real impressions data over the same time windows and grain.
- [ ] The `RevenueInterval` DTO's currency and gross/net/refund fields are exercised by at least one test with non-trivial values (a refund, a non-USD currency, or both) — not just a happy-path total.
- [ ] Fail-closed behavior confirmed for missing/invalid PoS credentials, matching Phase 11's pattern; credentials are read from a real secret store, not a plaintext `.env` value, in any shared/deployed configuration.

## Exit criteria

`APP_MODE=connected` produces real RPI figures using both real impressions (Phase 11) and real revenue (this phase), attributed per product identifier as the client's design specifies (Phase 10) — or, only if the chosen PoS system can't support that, a client-approved coarser fallback, explicitly labeled observational rather than causal.

## Dependencies

Phase 4 (`compute_rpi()`), Phase 6 (`APP_MODE`), **Phase 11b** (a real end-to-end RPI figure is only meaningful once real impressions exist to join against — this is a hard dependency, not just an "effectively" one; Phase 11 was split 2026-07-16 into 11a seam-port / 11b live conformer, and it's the live conformer this phase needs). The `RevenueDataSource` interface here should mirror 11a's provider-seam pattern.

## Open questions

(Local list — cross-referenced against the global numbering in `99-open-questions.md` in brackets.)

1. Which PoS/revenue system should the first real integration target? [global #3]
2. Can that chosen PoS system actually resolve sales by product identifier, matching the client's `AdPlayRecord` design (Phase 10) — or does the first live demo need the coarser store-day fallback from step 3? [global #4 — narrowed from a methodology question to a per-vendor capability check, now that the client has specified per-product-identifier lookup as the target]

> **Amended (workstream bluezoo-live-verification, 2026-07-25) — a tenant-config precedent this phase should follow.** The live BlueZoo scan (`working-docs/bluezoo-live-verification/findings.md`) established that BlueZoo's *base URL itself* is per-customer (cluster-scoped), not a constant, and that available tables are a per-account entitlement discovered at runtime via `list_tables`. Step 2's `RevenueDataSource` interface should assume the same shape for PoS: **endpoint/region and available capabilities are per-tenant configuration discovered or declared per deployment, not compiled-in constants** — the retailer's PoS instance will vary at least as much as BlueZoo's cluster does. Concretely: don't bake a vendor hostname into the adapter, and treat "this PoS can resolve by product identifier" (open question 2 above) as a per-tenant capability flag the adapter can degrade against, not a global yes/no answered once. Nothing else in this phase changes — BlueZoo provides no revenue data, so the scan has no direct bearing on the numerator.

> **Amended (workstream 11b, 2026-07-28) — inherit the startup-scan lesson before designing the revenue seam.**
>
> 11b discovered that `app/database/mock_data.py`'s Step 4 regenerates metrics unconditionally at startup, so a connected-mode `AudienceDataSource` is hit on **every process start**, not once per deployment. A `RevenueDataSource` built on the same pattern will inherit the same behavior — meaning every restart would also issue a **PoS call**, against a system that may be rate-limited, billed per query, or operated by a third party with its own opinions about traffic.
>
> Decide this deliberately rather than by default: either make startup seeding skip live providers in `connected` mode, or make the revenue read lazy/cached. Do not discover it in production. Detail and the audience-side consequences: the amendment at the foot of `13-production-hardening-live-mode.md`; record in `working-docs/11-live-bluezoo-adapter-conformer/WORK_LOG.md`.
