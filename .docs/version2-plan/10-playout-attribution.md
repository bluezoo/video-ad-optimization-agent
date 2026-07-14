# Phase 9 — Ad-Play Tracking / Exposure Attribution (Demo-Only)

## Goal

Give impressions a real structural basis — "this ad played on this screen during this time window, and this many sensor visits happened during that window" — instead of a flat random number attached directly to a video with no notion of screen or time. This is demo-only data, built from small, deterministic, BlueZoo-shaped fixtures (not a large synthetic time series), so it establishes the exact DTO shape and join logic Phase 10/11 need when real BlueZoo/PoS data replaces the fixture side.

## Update: the client specified this exact schema directly — this phase now implements the client's design, not an invented one

After this plan's first draft, the client sent a concrete architecture proposal for this exact phase (full text in `.docs/.context/project_context.md`). It resolves most of what was previously an open question here. Quoting the proposed input schema directly — an **ad-play record**, composed of:

- **sensor/screen identifier** `[string]` → links to BlueZoo's data warehouse
- **ad_name** `[string]`
- **product identifiers** `[string]`/`[numeric]` → links to the retailer's PoS data warehouse
- **start day/time** `[date-time]`
- **end day/time** `[date-time]`

The stated design: this record is produced by the retailer's **content management system (CMS)**, delivered on a **batch, end-of-day cadence** — not real-time. For each ad-play record, the reconciliation job then: (1) calls BlueZoo's API for impressions using the screen identifier + time window, and (2) calls the retailer's PoS system for revenue using the product identifier(s). The client's team will engage the retailer's CMS vendor directly to build the live feed — this app's job is to define and consume that contract, not to build the CMS integration itself.

This is good news for the plan's "don't overcomplicate" philosophy: it's an end-of-day batch job, not a real-time stream, and the client has already specified the exact schema this phase should build fixtures against.

## What this resolves from the first draft's open questions (and what's still open)

- **Resolved:** the join key is an **ad-play record** (screen + ad_name + product identifier(s) + explicit start/end window), not an ambiguous "video ID with no time context." the client's design calls BlueZoo's API using the ad-play's *own* start/end window directly — i.e., the intended approach is to query per-ad-play, not to pre-aggregate a 15-minute-grain time series and split it after the fact.
- **Narrowed, not eliminated:** the previous draft's "how do we split a shared 15-minute BlueZoo bucket across multiple rotating 8-second creatives" question is no longer a fundamental attribution-methodology question — the client's design implies calling BlueZoo per ad-play window directly. What's still open is a **narrower, technical** question: does BlueZoo's API actually return meaningful, non-duplicated counts for a query window shorter than its 15-minute historical grain (this likely means using the **Real-time API** — `get_occupancy_count`/`get_visits` — rather than the historical Data Warehouse `run_query` path, which is confirmed 15-minute grain)? This needs a direct technical check against BlueZoo's API (Phase 10), not a design decision — see open questions.
- **New:** revenue lookup is per **product identifier**, not per-store-day as this plan's first draft of Phase 11 had suggested as a fallback milestone. The client's design is more specific than that fallback — Phase 11 is updated to reflect this as the actual target, not just an aspirational one.

## Current state

Today, `_generate_mock_video_metrics()` (unified in Phase 4) assigns impressions/revenue directly to a video ID, with no concept of which physical screen it played on, during what time window, or which product it advertised. There is no ad-play record, no `screen` entity, and no join logic anywhere in the codebase. The current `video_metrics` table (`app/database/db.py:137-151`) stores one daily scalar per video, which can't represent sub-day, per-screen, per-product structure — this table shape needs to grow a level (screen/ad-play/interval), not just gain a new upstream input.

## Steps

1. Define an `AdPlayRecord` DTO **matching the client's schema exactly**: `screen_id: str`, `ad_name: str` (maps to this app's video/creative identifier), `product_id: str | int` (matches this app's `Product.id` from Phase 7), `start_time: datetime`, `end_time: datetime`. This is deliberately the same shape a live CMS feed will eventually produce — defining it here, against fixtures, is what makes a future live CMS/BlueZoo/PoS integration a data-source swap instead of a redesign.
2. Define a `BlueZooVisitInterval`-shaped DTO for the audience side — sensor/screen ID, a UTC timestamp (or interval), a visit/inner-count field (matching BlueZoo's actual `incoming_inner_count` field name and semantics), and any zone field BlueZoo's schema requires. Do not assume a fixed 15-minute grain is what gets queried per ad-play (see the narrowed open question above) — model this DTO to represent whatever interval BlueZoo's chosen endpoint actually returns.
3. Add a minimal `Screen` concept (id, name/location) — check whether `app/database/db.py` already has anything screen-adjacent first (`grep -n "screen" app/database/db.py`). A small number of screens (2-5) is enough — see open questions.
4. Generate a **small set of deterministic, hand-shaped fixtures**: a handful of `AdPlayRecord`s (matching the client's schema) across 2-5 screens and a few products, plus corresponding `BlueZooVisitInterval` fixture data for the same screens/windows. Not a generated-at-runtime large time series — a few days' worth of records is enough to prove the join logic.
5. Implement the join exactly as the client described it: for each `AdPlayRecord`, look up impressions by `(screen_id, start_time, end_time)` against the `BlueZooVisitInterval` fixtures, and look up revenue by `(product_id, start_time, end_time)` against Phase 4's revenue fixtures (formalized the same way). No cross-creative allocation formula needed for the demo fixtures, since each `AdPlayRecord` already has its own explicit, non-overlapping-by-construction window — but flag in code/comments that real CMS data arriving with overlapping windows on the same screen would need the narrowed technical question above resolved first (Phase 10).
6. Route the deterministic generator from Phase 4 to *derive* impressions and revenue via this join instead of assigning them directly — Phase 4's determinism moves one level down (the fixture data is what's seeded/deterministic; an ad-play's impressions/revenue become a computed consequence of the join).

## Validation

- [ ] Given a fixed seed, the `AdPlayRecord` and `BlueZooVisitInterval`/revenue fixtures are reproducible.
- [ ] The join function correctly attributes visit counts and revenue per `AdPlayRecord`'s exact `(screen_id/product_id, start_time, end_time)` window.
- [ ] An ad-play's total impressions/revenue match `compute_rpi()`'s expected input shape from Phase 3.
- [ ] `make test-unit`, `make test-e2e` pass with the new join logic; Phase 6's RPI-across-creatives comparison still produces sensible output using join-derived (rather than directly-assigned) impressions/revenue.

## Exit criteria

Impressions and revenue for any demo ad-play are a computed result of a join keyed on the client's exact `AdPlayRecord` schema against BlueZoo-shaped and revenue fixture data — and both DTOs are the same shape Phase 10/11 will populate from real APIs.

## Dependencies

Phase 3 (`compute_rpi()` contract), Phase 4 (this phase reroutes Phase 4's deterministic generator to derive impressions/revenue via the join, rather than assigning them directly — Phase 4 should be scoped as a narrower aggregate generator with this in mind, so its work isn't thrown away here), Phase 7 (`product_id` must key against the generic `Product` model, not fashion-specific fields).

## Open questions

1. **Does BlueZoo's API return accurate, non-duplicated counts for a query window shorter than its confirmed 15-minute historical grain** (likely meaning the Real-time API — `get_occupancy_count`/`get_visits` — needs to be used for per-ad-play queries, rather than the Data Warehouse `run_query` path)? This is now a technical verification question for Phase 10, not an open design question — the client's design already specifies querying per ad-play window directly.
2. **What is the CMS vendor's actual delivery mechanism and format for the end-of-day ad-play feed** — a file drop, a webhook, a polling API? The client's email states their team will engage the retailer's CMS vendor to build this, so the exact contract may not be known yet — flag as pending on that engagement, and build Phase 9's fixtures to match the schema already given, regardless of transport mechanism.
3. How many screens should the demo simulate, and does BlueZoo (or the client specifically) have a preferred number/layout to make the demo feel realistic for a specific prospect walkthrough? Not a blocker — any reasonable small number (2-5) is fine to start.
