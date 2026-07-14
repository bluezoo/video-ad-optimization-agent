# Phase 4 — Deterministic Demo Data

## Goal

Replace the two independently-drifted random-metric generators (called from three separate places) with a single, deterministic generator, so demo numbers are reproducible and internally consistent regardless of which code path created them.

## Current state (confirmed live bug — corrected to three call sites, not two)

Two separate functions named `_generate_mock_video_metrics()` exist and disagree, and there are **three** call sites across them, not two:

- `app/database/mock_data.py:168-235` — impressions range 800-2000, `revenue_per_impression = random.uniform(0.02, 0.08) * multiplier`. Called from `populate_mock_data()` at line 382. **Its date window runs backward from today** (`mock_data.py:188`) — i.e., "the last N days."
- `app/tools/review_tools.py:454-513` — a **completely separate implementation**, impressions range 800-1500, RPI range $0.08-$0.15. Called from two places: `activate_video()` at `review_tools.py:166`, **and** `generate_additional_metrics()` at `review_tools.py:550` (this second call site was missed in the first draft of this phase). **Its date window runs forward from a supplied start date** (`review_tools.py:484`) — the opposite direction from the seed-time generator.

Result: two videos activated in the same demo session, seeded from the same "mock data," can show RPI figures that differ by nearly 2x purely because of which function happened to generate them — a visible inconsistency in a live demo, and a correctness problem for the RPI-across-creatives comparison Bill specifically asked about (Phase 6 depends on this being fixed first). **A single shared seed alone does not fix this** — the two generators don't just disagree on RNG ranges, they disagree on which direction time runs, so unifying them requires deciding on one anchor-date-and-direction model, not just one RNG.

## Steps

1. Delete both existing implementations and write a single new `generate_mock_metrics(seed, ...)` function used by all three call sites. Use Python's `random.Random(seed)` (a local, seeded instance) rather than the global `random` module, so calls are reproducible without affecting global RNG state used elsewhere in the process.
2. **Reconcile the date-window semantics first** — this is the part a shared seed alone doesn't solve. Pick one fixed demo anchor date (e.g., "today" at the moment the demo DB is seeded) and one explicit rule for how a video's metrics window extends from it (e.g., always the N days *before* the anchor, regardless of whether the video was seeded at DB-init time or generated later at activation time). Both `populate_mock_data()`'s backward-from-today window and `activate_video()`/`generate_additional_metrics()`'s forward-from-start-date window need to be rewritten to follow this one rule, not just call a shared RNG with their existing, conflicting date logic left in place.
3. Derive the seed deterministically using a **stable, cross-process hash** — e.g., `hashlib.sha256(f"{video_id}".encode()).hexdigest()` truncated/converted to an int — not Python's built-in `hash()`, which is randomized per-process (`PYTHONHASHSEED`) by default and would silently break the "same input, same output across runs" guarantee this phase exists to provide.
4. Fold in the RPI range decision: pick one canonical range (recommend keeping close to the more realistic-looking of the two, but this is a product/demo-realism call, not a technical one — flag if unsure) and use it consistently. Compute the stored RPI figure via `compute_rpi()` from Phase 3, not an inline `revenue_per_impression` multiplication, so the generator and the display layer can never disagree.
5. Update all three call sites (`app/database/mock_data.py:382`, `app/tools/review_tools.py:166`, `app/tools/review_tools.py:550`) to use the single new function.
6. Remove both now-dead duplicate functions entirely — do not leave either in place "for compatibility"; nothing external calls them directly (confirm via `grep -rn "_generate_mock_video_metrics" app/ tests/`).

## Validation

- [ ] Calling the new `generate_mock_metrics()` twice with the same seed produces identical output (determinism test) — including across separate process runs (proving the SHA-256-based seed, not `hash()`, is actually being used).
- [ ] Calling it with two different seeds (e.g., two different `video_id`s) produces different-but-plausible output (not degenerate/constant).
- [ ] A demo run that seeds a campaign via `populate_mock_data()` and then activates one of its videos via `activate_video()` shows RPI figures consistent with `compute_rpi()`, with no visible discontinuity between "seeded at DB init" and "generated at activation time" data — and both use the same date-window rule from step 2.
- [ ] `generate_additional_metrics()` (`review_tools.py:550`) also uses the unified generator — a test confirms this third call site wasn't missed.
- [ ] `grep -rn "_generate_mock_video_metrics"` returns zero hits (both functions fully removed, not just unused).
- [ ] `make test-unit` and `make test-e2e` pass; update any test fixture that depended on the old RNG ranges or the old date-window behavior.

## Exit criteria

One deterministic mock-metrics generator, used by every code path that needs mock data, producing RPI values via the Phase 3 shared `compute_rpi()` function.

## Dependencies

Phase 3 (needs `compute_rpi()` to exist).

## Open questions

Which RPI range is the "right" one for demo realism — `mock_data.py`'s $0.02-$0.08 or `review_tools.py`'s $0.08-$0.15? This is a product decision (what looks credible in front of Bill/prospects), not a technical one. Flagging rather than picking arbitrarily.
