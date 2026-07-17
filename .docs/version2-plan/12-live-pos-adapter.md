# Phase 11 — Live Revenue / PoS Adapter

## Goal

Build a real `RevenueDataSource` so RPI's numerator (revenue) can come from an actual point-of-sale or attribution system, the same way Phase 10 makes the denominator (impressions) real. Today, revenue is 100% synthetic (`app/database/mock_data.py`), and there is no PoS/revenue integration of any kind, confirmed via repo-wide grep.

## Update: the client's ad-play-tracking design (see Phase 9) specifies the attribution key — per product identifier, not per-store-day

Per the client's email (full text in `.docs/.context/project_context.md`), each `AdPlayRecord` carries its own `product_id`, and the end-of-day reconciliation job looks up revenue for that ad-play by product identifier + time window against the retailer's PoS data warehouse. This resolves what was previously an open attribution-methodology question in this plan's first draft: **per-product-identifier revenue lookup is the specified design, not an aspirational stretch goal beyond a coarser store-day fallback.** Step 3 below is updated accordingly — the store-day milestone is now a fallback to reach for only if the chosen PoS system genuinely can't support product-level lookups, not the default recommended first target.

## This phase is more open-ended than Phase 10 — read the open questions first

Unlike BlueZoo's audience data (one well-documented API this plan has already fetched and verified), there is no equivalent "the revenue source" — it depends entirely on which point-of-sale or e-commerce system an actual BlueZoo customer uses, and whether that system exposes sales by product identifier (the client's design assumes it does — this needs confirming against whichever PoS system is chosen, not treated as guaranteed for every retailer). This is still partly a **business/integration question** (which PoS system, what access), even though the attribution methodology itself is now specified.

## Current state

- `revenue` in `video_metrics` (`app/database/db.py:139-151`) is entirely synthetic (`_generate_mock_video_metrics()`, being unified in Phase 4).
- No PoS, e-commerce, or payments integration exists anywhere in the codebase.
- BlueZoo's own API does not provide revenue data — it's an audience/attention measurement platform (confirmed via Phase 2's research), so this is necessarily a separate integration, not something bundled with Phase 10.

## Steps

1. **Resolve with the client which PoS/revenue system to target first** — this determines everything else in this phase (Square, Shopify, a generic CSV/webhook ingestion path, or something specific to a BlueZoo pilot customer). Do not start building against a specific vendor's API without this confirmed. As part of this, confirm the chosen system can look up sales **by product identifier** — the client's `AdPlayRecord` design (Phase 9) assumes this is possible; if the first target system can't do it, that's a real gap to flag back to the client, not something to quietly work around.
2. Once a target is chosen, define a `RevenueInterval` DTO and a `RevenueDataSource` interface analogous to Phase 10's `AudienceDataSource`. **Correction from review: a bare `get_revenue(id, start, end) -> float` is too small to align real PoS data reliably** — it omits currency, gross-vs-net/refund/tax handling, store/SKU identifiers, event timezone, and source transaction identity, all of which the current schema also lacks (`video_metrics.revenue` is a single undifferentiated `REAL` column, `app/database/db.py:146`). Define the DTO with at least: amount, currency, gross/net/refund basis (explicitly, not assumed), store/SKU key(s) (this is where `product_id` from Phase 9's `AdPlayRecord` plugs in directly), a UTC timestamp or interval, and a source transaction ID for idempotency — even if the first real adapter only populates a subset of these, the interface should not preclude them.
3. **Build the real adapter to look up revenue per product identifier + time window, matching the client's `AdPlayRecord` design (Phase 9) — this is the specified target, not an aspirational one.** Fall back to a coarser store × day (or store × 15-minute bucket, matching Phase 9/10's grain) milestone only if the chosen PoS system genuinely cannot resolve sales by product identifier — and if that fallback is needed, get the client's explicit sign-off that a coarser, clearly-labeled **observational** (not causal) store-day number is an acceptable substitute before shipping it as the first live integration.
4. Implement `DemoRevenueDataSource` (wraps Phase 4's deterministic synthetic revenue, unchanged) and the real adapter for whichever system is chosen, both behind the same interface, wired to `APP_MODE` exactly as Phase 10 wires `AudienceDataSource`.
5. **Minimum live-secret handling belongs in this phase, not deferred to Phase 12** — same correction as Phase 10, step 6: read PoS credentials from a real secret store from the start, not a plaintext `.env` file migrated later.

## Validation

- [ ] `DemoRevenueDataSource` and the real adapter both pass a shared contract test suite (same pattern as Phase 10).
- [ ] With `APP_MODE=connected`, revenue data flows into `compute_rpi()` (Phase 3) correctly, joined against Phase 10's real impressions data over the same time windows and grain.
- [ ] The `RevenueInterval` DTO's currency and gross/net/refund fields are exercised by at least one test with non-trivial values (a refund, a non-USD currency, or both) — not just a happy-path total.
- [ ] Fail-closed behavior confirmed for missing/invalid PoS credentials, matching Phase 10's pattern; credentials are read from a real secret store, not a plaintext `.env` value, in any shared/deployed configuration.

## Exit criteria

`APP_MODE=connected` produces real RPI figures using both real impressions (Phase 10) and real revenue (this phase), attributed per product identifier as the client's design specifies (Phase 9) — or, only if the chosen PoS system can't support that, a client-approved coarser fallback, explicitly labeled observational rather than causal.

## Dependencies

Phase 3 (`compute_rpi()`), Phase 5 (`APP_MODE`), **Phase 10b** (a real end-to-end RPI figure is only meaningful once real impressions exist to join against — this is a hard dependency, not just an "effectively" one; Phase 10 was split 2026-07-16 into 10a seam-port / 10b live conformer, and it's the live conformer this phase needs). The `RevenueDataSource` interface here should mirror 10a's provider-seam pattern.

## Open questions

(Local list — cross-referenced against the global numbering in `99-open-questions.md` in brackets.)

1. Which PoS/revenue system should the first real integration target? [global #3]
2. Can that chosen PoS system actually resolve sales by product identifier, matching the client's `AdPlayRecord` design (Phase 9) — or does the first live demo need the coarser store-day fallback from step 3? [global #4 — narrowed from a methodology question to a per-vendor capability check, now that the client has specified per-product-identifier lookup as the target]
