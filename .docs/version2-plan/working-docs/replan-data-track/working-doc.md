# Workstream: replan-data-track (docs only)

**Branch:** version_2_replan-data-track
**Trigger:** owner's strategic pivot + sibling-repo findings (`.docs/.context/2026-07-16-sibling-repo-reassessment.md`, local). Enforced trigger from that review: Phase 4 may not start until this replan merges.
**Deliverable:** a PR of amended plan docs — no code.

## Research findings (from the 7-agent reassessment, 2026-07-16)

- `/Users/lavi/gwork/ad-campaign-agent` (owner's personal repo) is this repo's upstream donor: the client repo was seeded mid-June from a squashed snapshot; the donor then continued ~97 unpushed commits containing a working `AudienceProvider` seam (entry-point registry, in-memory + BQ-backed synthetic providers), a deterministic hash-seeded BlueZoo-shaped generator (5 tables, 15-min grain), sqlglot `QueryGuard`, and a dual-write activation→attribution bridge. This is material evidence on open question Q1.
- Neither repo has live BlueZoo connectivity (schema-shape only) nor any product/image ingestion path — from-scratch onboarding is new work everywhere.
- The donor is a **donor, not a transplant**: dormant since May, unpushed dirty flagship branch, missing Phases 0/1 fixes, fashion-hardcoded, GCP-billed-project default.

## Owner decisions (2026-07-16, recorded verbatim-in-spirit)

1. **One-system principle (Q2 direction):** demo and live must not be two systems — demo providers mimic BlueZoo's API + database schema behind one seam; the live connector drops in behind the same interface. BlueZoo's actual schema/API docs are needed to validate the mimic (ask client; blocks only the live conformer).
2. **Onboarding: both, tools first.** Agent tools are primary (`create_product`, `import_products_from_folder`, `generate_product_image` via nano banana); a thin CLI wrapper over the same functions serves scripted/bulk setup.
3. **Local-first storage:** product images and generated videos save/load locally; GCP credentials are needed only for model calls (Gemini/Veo/nano banana). GCS becomes an explicit opt-in for cloud deploys; the personal-bucket default (`app/config.py:52-53`) is removed.
4. **Phase 4 fate (owner delegated; call made):** rewrite as "port the donor generator, conformed to BlueZoo shape; retire both existing mock generators." Prime motive stated by owner: general agent + closest possible alignment with BlueZoo data schema and metrics.

## Implementation approach (the amendments)

1. `05-deterministic-demo-data.md` (Phase 4) — rewrite around porting the donor's `seed.py`.
2. `06-app-mode-config-skeleton.md` (Phase 5) — `APP_MODE` resolves to an internal provider name (one config axis); un-protect import-time `populate_mock_data()` (seeding becomes explicit, idempotent, gated).
3. `08-product-schema-generalization.md` (Phase 7) — flip step 6: product CRUD is real, lives in the new onboarding phase.
4. `10-playout-attribution.md` (Phase 9) — fixtures come from the ported generator; adopt the donor's dual-write bridge + attribution-join pattern; adopt the BlueZoo 5-table shape.
5. `11-live-bluezoo-adapter.md` (Phase 10) — split 10a (port the seam now — unblocked) / 10b (live conformer — blocked on BlueZoo schema/API docs).
6. New `15-product-onboarding.md` (Phase 14) — tools-first onboarding + local storage write path + kill personal-bucket default + preseeded fashion becomes a selectable dataset.
7. `99-open-questions.md` — Q1 ancestry evidence; Q2 reframed to one-system/mimic-first; Q8 answered yes; Q16 resolved by local-first decision.
8. `00-overview.md` — phase table, dependency edges, philosophy updates.

## Test plan

Docs-only: verification = internal consistency greps (no dangling references to retired plans, dependency edges match STATUS, new phase in overview table + 99 consolidation) and owner review of the PR diff. No demo scenario applies (no code changes).

## Out of scope

- Any code change (the amended phases do the porting later).
- Renumbering phases, restructuring to the donor's `services/` layout wholesale, packaging migration (uv), FastAPI composition — all explicitly deferred decisions, not silently adopted.
- Phases 12 (live PoS), 13a/13b docs — untouched beyond dependency-line touch-ups if strictly required.
