# Workstream 10: playout-attribution

**Branch:** version_2_playout-attribution
**Phase doc:** .docs/version2-plan/10-playout-attribution.md (Phase 9)

## Research findings

Full detail (with the four DISCOVERY entries) in this directory's `WORK_LOG.md`; the load-bearing facts:

1. **The phase doc's "Current state" predates ws05** (amended with provenance this branch). The real current state: `app/demo_data/seed.py` generates BlueZoo-shaped frames (15-min grain, hash-seeded, `ad_campaign_id` naming) → `app/demo_data/derive.py` collapses them into per-video-per-day `video_metrics` rows → two call sites write those rows: `app/tools/review_tools.py` (`_insert_derived_metrics` at :113-131, used by video activation at :35 and `generate_additional_metrics` at :117) and `app/database/mock_data.py:343` (seed-time bulk generation — no activation moment exists on that path). `derive.py`'s own header declares this phase replaces it with the ad-play join; `seed.py` stays untouched (owner note (a) confirmed).
2. **seed.py already carries most of the raw material.** `SeedConfig.screen_ids: list[int]` (seed.py:70) is genuine multi-screen support — every frame loops over screens; only `derive.py:_campaign_seed_config()` (:21-38) collapses it to the 1:1 campaign-as-screen proxy. And seed.py:239-254 already emits a dormant `video_attribution` frame — `(video_id, ad_campaign_id, screen_id, active_from, active_to)`, exactly the donor bridge's window shape — that nothing consumes yet. `BLUEZOO_MAPPING.md` pre-reserves that frame name for this phase.
3. **Per-creative RPI (owner note (b)):** `derive.py:video_rpi()` (:61-70) = `DEMO_RPI` × seeded factor in [0.6, 1.4] → band [0.03, 0.07], keyed per `(ad_campaign_id, video_id)`, day- and screen-independent (ws07 owner decision). Demo scenario F4 and demo_guide journeys B4/B5 pin "not all creatives identical" and "one stable RPI constant per creative" — these are hard invariants for the join world.
4. **Consumers are insulated if `video_metrics` keeps its shape.** All 8 reader paths (`metrics_tools.py` :200-243, :339-380, :505-592, :684-704, :792-805; `review_tools.py` :390-393, :808-827) issue raw SQL aggregations against the existing columns. `test_metrics_tools.py` raw-INSERTs its fixtures. Only `tests/unit/test_demo_derive.py` imports derive internals by name and must be rewritten.
5. **Donor bridge mapped** (read-only `/Users/lavi/gwork/ad-campaign-agent`): `write_video_attribution(video_id, campaign_id, store_id, active_from)` / `close_video_attribution(video_id, store_id, active_to)` (provider.py:135-152); 5-column window table; open row = `active_to IS NULL`; close targets the earliest open row and **silently no-ops on miss**. Port renames: `store_id`→`screen_id`, `campaign_id`→`ad_campaign_id`. We will NOT inherit the silent no-op (this repo's review tools return explicit errors) and will NOT port the donor's attribution-adjacent query math (inner+outer double-count bug — ws05 fixed it here; `test_demo_derive.py:29-43` pins inner-only).
6. **Client contract** (project_context.md:61-72, Email 5): `AdPlayRecord` = sensor/screen identifier, ad_name, product identifiers, start/end day/time, delivered by CMS as end-of-day batch. `BlueZooVisitInterval` scoped to `sensor_visits` fields only; no sub-15-min window assumptions (owner note (c) — replan amendments honored). `Product.id` is `int | None` (product.py:28); we key by int.
7. **Gaps the phase doc misses:** no join story for `dwell_time_seconds` and `circulation` (decision below); `BLUEZOO_MAPPING.md` has a stale "flat 0.05" RPI line (one-line fix bundled here).

## Implementation approach

**Big picture:** `video_metrics` stays exactly as it is — a per-video-per-day *derived aggregation* (replan amendment 2). What changes is *how its numbers are produced*: instead of `derive.py` inventing per-video-per-day scalars (visits × `video_fraction()`, revenue = impressions × RPI, all keyed to a fake campaign-as-screen), the pipeline becomes:

```
activation windows (video_attribution table)          ← dual-write bridge, ported donor shape
    → deterministic ad-play schedule (AdPlayRecord)   ← client contract DTO, computed not stored
    → join: plays × sensor visit-intervals (impressions) × revenue fixtures (revenue)
    → daily aggregation → same video_metrics rows, same two call sites
```

### Components

1. **DTOs — `app/models/attribution.py`:** Pydantic `AdPlayRecord` (screen_id, ad_name/video_id, ad_campaign_id, product_ids, start, end — client-contract fields per Email 5) and `BlueZooVisitInterval` (timestamp, screen_id, incoming_inner_count + the other `sensor_visits` fields — scoped exactly per replan amendment). These are the typed contracts the join consumes; they exist so Phase 11's connected mode can produce the same shapes from real BlueZoo/CMS data.
2. **DB — one new table `video_attribution`** in `db.py`: `(id, video_id FK, ad_campaign_id, screen_id, active_from NOT NULL, active_to NULL)` — the ported donor shape with renamed keys, and the persistent thing the bridge writes. Open window = `active_to IS NULL`.
3. **Dual-write bridge in `review_tools.py`:** activation opens window rows (one per screen the campaign plays on); pause/archive close them (`active_to = now`). Close-on-miss logs a warning and continues (activation predating the bridge is legitimate) — but never the donor's silent swallow.
4. **Screens — deterministic roster, no DB table:** each campaign gets 2–3 screens (e.g. entrance/aisle/checkout) via the same sha256-seeded derivation seed.py uses, exposed from `app/demo_data/` as a small helper. This decouples screen_id from ad_campaign_id (killing the 1:1 proxy) and feeds `SeedConfig.screen_ids` its real multi-screen list. Phase 11 maps real sensor IDs onto this; a `screens` DB table would be schema nobody reads yet (rejected below).
5. **Join — `app/demo_data/attribution.py`:** expands each window into per-day `AdPlayRecord`s (a seeded handful of 15-min-aligned play slots per (video, screen, day) — non-overlapping per screen by construction, since one screen plays one ad at a time); joins plays against `generate_frames()`'s `screen_visits` (inner counts only) for impressions; joins against revenue fixtures for revenue; aggregates to daily rows.
6. **`derive.py` rewritten in place as the facade:** `derive_video_metrics_rows(...)` keeps its signature and both call sites stay untouched; its internals route through windows → plays → join. `video_rpi()` survives (revenue side, per-creative differentiation); `video_fraction()` dies — the visit share now *emerges* from how many slots each video actually played; `campaign_uplift()` survives inside the seed config. `mock_data.py`'s bulk path seeds windows for pre-activated videos (active_from = anchor − 30d) before deriving — the dormant seed frame already generates exactly this shape.
7. **Revenue fixtures preserve per-creative RPI:** the fixture generator produces per-(product, window) revenue rows *as a function of the play schedule* — revenue for a play window = visits in that window × `video_rpi(ad_campaign_id, video_id)`. Realistic direction (PoS revenue occurs because the ad played), keeps the client's join shape (revenue looked up by product + time window), and keeps F4's invariant: summing any creative's rows and dividing (via `compute_rpi`) recovers that creative's stable RPI constant exactly.
8. **dwell/circulation stay synthetic** (phase-doc gap): dwell keeps its seeded RNG, circulation derives from `outgoing_outer_count` over the played slots — both attached to the play windows now, real semantics deferred to Phase 11 per METRICS.md:45.

### Alternatives considered and rejected

- **Delete derive.py, new public API, touch both call sites** — pure churn: the two callers and 8 readers are all insulated by the current signature/table shape; "replaces this file" (its header) means replacing the *assumptions*, which a rewrite-in-place does. Rejected.
- **`screens` DB table now** — no reader tool needs screens yet; a table would be dead schema until Phase 11, which is the phase that actually learns real sensor IDs. Deterministic roster in `app/demo_data/` gives the same decoupling with zero migration. Rejected (flagged — easy to add later).
- **Persist `AdPlayRecord`s in a DB table** — plays are demo fixtures, fully reproducible from (windows + seed); storing them duplicates state nobody queries and the phase doc asks for fixtures, not storage. The DTO is the contract. Rejected.
- **Product-day revenue pool apportioned across creatives** — purer "revenue is product-keyed" modeling, but when two creatives advertise the same product, apportioning collapses per-creative RPI differentiation unless the apportioning itself is play-weighted — at which point it's the recommended approach with extra steps. Rejected.

## Test plan

- **Unit (new):** `tests/unit/test_demo_attribution.py` replacing `test_demo_derive.py` — window→play expansion determinism (same seed → identical plays, different creatives → different schedules); join arithmetic (impressions = sum of inner visits over played slots; revenue = play visits × video_rpi); per-creative RPI invariants carried over (band [0.03, 0.07], `compute_rpi` over any creative's rows recovers its constant, not-all-identical across creatives); bulk-seed path windows (30 days back from anchor, still open); bridge unit tests (activate opens N-screen windows, pause/archive closes them, close-on-miss warns).
- **Existing suites:** `make test-unit` + `make test-e2e` green throughout (PostToolUse hook enforces unit on every edit). `test_metrics_tools.py` must pass unmodified — that's the "consumers untouched" proof.
- **Demo scenarios (verifying-with-demo-scenarios):** F3 (generate additional metrics — 30→33 days) and F4 (RPI-across-creatives chart — differentiation + stable constants) from `docs/demo-scenarios/fashion.md` must PASS, plus one new scene asserting attribution windows exist post-activation and metrics only accrue inside them.
- **demo_guide.md refresh (owner note (d)):** journeys re-walked; B4/B5 invariants unchanged but narrative + example values refreshed; new "what changed in Phase 10" note. Synced to main checkout before the PR.

## Out of scope

- Real BlueZoo/CMS/PoS connectivity or `APP_MODE=connected` provider wiring (Phase 11) — this phase produces the *shapes* Phase 11 fills.
- Real dwell/circulation semantics (Phase 11; documented gap decision above).
- A `screens` DB table or screen-management tools (revisit when Phase 11 brings real sensor IDs).
- Any change to `seed.py`'s frame generator (owner note (a)) beyond feeding it real multi-screen `screen_ids` via existing config.
- `video_metrics` schema changes — replan amendment 2 keeps it as the derived aggregation.
- Sub-15-min play windows or live-window queries (replan amendment; play slots are 15-min-aligned).
- README.md / DEMO_GUIDE.md (untouched per standing rules).
