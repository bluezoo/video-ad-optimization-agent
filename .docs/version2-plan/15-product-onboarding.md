# Phase 15 — From-Scratch Product Onboarding (local-first)

> **New phase (workstream replan-data-track, 2026-07-16), from the owner's strategic pivot.** The demo must be startable from zero: no preseeded fashion catalog, no preseeded media — a fresh set of product images (or none at all, generating them) is enough to reach campaigns, video generation, and BlueZoo-shaped analytics. Neither this repo nor the donor (`ad-campaign-agent`) has any product/image ingestion path today; this is genuinely new work. Owner decisions recorded 2026-07-16: **tools-first onboarding** (agent tools primary, thin CLI wrapper over the same functions) and **local-first storage** (product images and generated videos save/load locally; GCP credentials only for model calls; GCS becomes an explicit opt-in for cloud deploys).

## Goal

A brand-new vertical can be onboarded end-to-end **by talking to the agent**: import a folder of product images (or generate product images from descriptions via the image model), get real `Product` rows, create campaigns, generate videos, and see deterministic BlueZoo-shaped analytics — with zero preseeded data and zero cloud-storage account.

## Current state (what blocks from-scratch today)

- **No write path for product images:** `app/storage.py` is read-only for `product-images/` — there is no `save_product_image()` anywhere; the personal GCS bucket default (`app/config.py:52-53`, `kaggle-on-gcp-ad-campaign-assets`) is a silent hard dependency, and `storage.py:189/208/224` raise without a real bucket/client.
- **No product creation path:** products exist only via `products_data.py` seed fixtures (Phase 8 keeps it that way by design; its step 6 explicitly routes CRUD here).
- **Unconditional import-time seeding:** `app/agent.py:111` calls `populate_mock_data()` at import — a from-scratch start is currently impossible; the fashion catalog always materializes (Phase 6's amendment marks this as scheduled to change here).
- The donor's setup wizard doesn't solve this — it installs a pre-built, manifest-verified asset bundle (Drive zip → user's bucket); its *wizard/manifest design* is worth borrowing for whatever optional demo bundle remains, but it has no ingestion path either, and its storage design is GCS-mandatory (do not inherit that).

## Steps

1. **Local-first storage backend.** Introduce a minimal storage seam in `app/storage.py`: a local-filesystem backend (default — images/videos under a configurable app data dir) and the existing GCS backend as explicit opt-in (`GCS_BUCKET` set → GCS; unset → local; never a personal-bucket fallback — delete the default at `app/config.py:52-53`, and make video-generation paths (`app/tools/video_tools.py:520` consumption) work through the seam. This resolves open question 16: demo mode requires GCP credentials **only for model calls**, no storage account.
2. **Gate seeding.** Replace `app/agent.py:111`'s unconditional `populate_mock_data()` with explicit, idempotent, gated seeding: runs only in demo mode **and** when the DB is empty **and** a demo dataset is selected (the 22-product fashion catalog becomes one selectable dataset, e.g. `DEMO_DATASET=fashion|none`, default preserving today's behavior for existing demos). `DEMO_DATASET=none` yields an empty catalog — the from-scratch start.
3. **Onboarding agent tools** (primary interface, per owner decision): `create_product` (name, category, description, attributes dict → Phase 8's typed `Product`), `import_products_from_folder` (local folder of images; filename/subfolder conventions → products + stored images through the step-1 seam), and `generate_product_image` (no image on hand: generate via the configured image model — nano banana per Phase 14a — and store it as the product's primary image). Wire into the Campaign agent's toolset with instruction text; follow existing tool conventions in `app/tools/`.
4. **Thin CLI wrapper** (secondary, per owner decision): `scripts/onboard_products.py` calling the *same functions* as the tools (no duplicated logic) for scripted/bulk/CI setup.
5. **Analytics attach automatically:** nothing to build if Phases 5/10/11a landed correctly — the hash-seeded generator yields deterministic BlueZoo-shaped data for any `(campaign, screen, date)` key, so a freshly onboarded product's campaign gets plausible metrics with zero fixture authoring. Add a test proving exactly this (onboard → campaign → metrics present and deterministic).
6. **Demo scenario:** write `docs/demo-scenarios/from-scratch-onboarding.md` — empty catalog → import/generate products conversationally → campaign → video generation → RPI analytics — and verify via `verifying-with-demo-scenarios`. This scenario doubles as the client-facing "works for any vertical, from zero" proof.

## Validation

- [ ] With `DEMO_DATASET=none` and no `GCS_BUCKET`: app starts with an empty catalog, no GCS client is ever constructed, and `import_products_from_folder` + `create_product` + `generate_product_image` produce retrievable typed `Product`s with locally stored images.
- [ ] Full from-scratch flow passes the new demo scenario (tool-call trace evidence, per the verification skill).
- [ ] Freshly onboarded product → campaign → deterministic metrics (step 5 test), RPI via `compute_rpi()`.
- [ ] Existing fashion demo unchanged under the default dataset selection (regression).
- [ ] CLI wrapper onboards the same folder identically (shared-function test, no logic drift).
- [ ] `make test-unit`, `make test-e2e` pass; `grep -rn "kaggle-on-gcp" app/` returns zero hits.

## Exit criteria

`DEMO_DATASET=none` + a folder of images (or none, generating them) reaches campaigns, videos, and BlueZoo-shaped analytics purely through agent tools, storing all assets locally — and the preseeded fashion demo remains one flag away for existing walkthroughs.

## Dependencies

Phase 8 (typed `Product` + adapter), Phase 9 (vertical-neutral prompts — otherwise onboarded non-fashion products generate fashion-flavored media), Phase 11a (provider seam so metrics attach through the one system). Informed by the donor's wizard/manifest design for any optional bundled demo assets. Independent of 11b/12/13 (nothing live required).

## Open questions

1. Image expectations for `import_products_from_folder`: minimum resolution/format constraints worth enforcing at import (the video pipeline consumes these images downstream)? Default: accept common formats, warn on tiny images, don't block.
2. Does the client want the fashion bundle to remain the *default* demo dataset after this phase, or should a from-scratch walkthrough become the primary demo story? Cosmetic, decide at demo-prep time.
