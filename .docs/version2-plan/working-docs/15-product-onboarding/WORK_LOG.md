# Workstream 15 — product-onboarding — WORK_LOG

Phase doc: `.docs/version2-plan/15-product-onboarding.md` (from-scratch product onboarding, local-first).

## 2026-07-22 — checkpoint 1: kickoff, worktree created

- Worktree `.claude/worktrees/version_2_product-onboarding`, branch `version_2_product-onboarding`, base `version_2` @ ed2b8ce (merge-base verified).
- STATUS.md row 15 → `kickoff in progress` (main checkout, commit af8f170).
- Dependencies checked in STATUS.md: Phase 8 (5d3e1f8), Phase 9 (20d7347), Phase 11a (4e0ce6a) — all `merged`.
- Owner kickoff directives (verbatim from request): "The doc carries three load-bearing amendments to honor: the ws09 owner directive under step 1 (nothing to/from GCS in local/demo mode — videos and charts included; demo assets ship as an auto-downloaded Drive bundle; tool responses must never emit storage.googleapis.com URLs), the ws08 amendments (both broken-image call sites — list_products unchecked URLs and generate_video_from_product's silent no-reference path — must route through the new storage seam; db.insert_product(Product) is the ready substrate the onboarding tools wrap), and gated seeding replacing app/agent.py's unconditional populate_mock_data() (DEMO_DATASET=fashion|none). New journeys go in root DEMO_GUIDE.md per the ws11a rule. ultracode"
- Research (checkpoint 1 amendment slot): pending.

## 2026-07-22 — checkpoint 1 amendment: kickoff research done

Ultracode workflow `ws15-kickoff-research` (3 parallel sonnet readers, 511k tokens). Essentials:

- **Storage surface:** product-images has NO write path and its 3 storage.py functions are GCS-only (raise sites :189/:208/:224 verbatim-correct); save_image/save_video already have local branches (template for the seam). GCS client fully lazy. Personal-bucket default now at config.py:72-73 (drifted from cited 52-53). `storage.googleapis.com` has ONE construction site (storage.py:370) but FOUR tool surfaces: video_tools.list_products (:1771, URL :1802, still unchecked), review_tools.get_video_review_table (:686-692), review_tools.get_video_details (:858-868), maps_tools (:482/:515/:520/:529). Charts already never touch GCS locally (ADK artifact service; only deploy.sh wires gs:// artifacts). Videos dual-write: storage-or-handrolled-local + tool_context.save_artifact — ADK artifacts is the established local-serving pattern; video_tools hand-rolls storage.save_video's local branch (:580-587 thumbnail, :655-662 video) — duplication to remove. No image-GENERATION tool exists in image_tools.py (analysis only); the precedent is generate_scene_image (video_tools.py:196, model=IMAGE_GENERATION=gemini-3-pro-image, returns bytes). No static-file serving layer exists anywhere. Landmines: worktree app/.env hardcodes GCS_BUCKET=kaggle-…; mock_data.py:77 comment contains "kaggle-on-gcp" (validation grep needs it scrubbed); image_tools.py:270 reads raw env GCS_BUCKET.
- **Product/seeding surface:** Product.image_filename is REQUIRED (no default) — create_product must handle placeholder-or-sequence; insert_product(db.py:412) accepts nonexistent image files, raises sqlite3.IntegrityError on UNIQUE name (tools must translate). **init_database() itself (db.py:259-261) unconditionally seeds 22 fashion + 6 retail products — gating only agent.py's populate_mock_data() will NOT yield an empty catalog** (DISCOVERY below). config.py:23-24 policy comment: APP_MODE is the ONLY mode knob — DEMO_DATASET must be framed as a demo-scoped dataset selector, with that comment amended. Tool convention: status/message/data/next_steps. list_products lives on the MEDIA agent; phase doc wires onboarding tools onto the CAMPAIGN agent (owner decision — noted, followed). Analytics-attach claim HOLDS end-to-end (attribution fully campaign-id-keyed; campaign_uplift docstring even anticipates Phase 15; test_retail_products proves insert→campaign already). No empty-DB pytest fixture exists — new one needed. CLI precedent: scripts/smoke_media_models.py style.
- **Donor/docs:** donor wizard (scripts/setup.py step_assets :456-536): gdown Drive download + zip extract + manifest.json {version, files: sha256 map} verify + StateFile idempotence — design borrowable; its GCS-upload tail is not. Donor's own Drive ID is flagged a pre-merge placeholder — treat as design, not proven code. gdown is a NET-NEW dependency for this repo. Q16 RESOLVED local-first (bar = ws09 directive). 14a NOT needed: IMAGE_GENERATION already gemini-3-pro-image via the same call path; drop-in beneficiary later. ws09 left resolve_archetype() as an anticipated extension point for generate_product_image — phase doc never mentions it; explicit design decision required. Phase 15 rated Medium. Scenario conventions per fashion.md; journeys → root DEMO_GUIDE.md.

## 2026-07-22 — DISCOVERY: gating populate_mock_data() alone cannot produce an empty catalog
Assumed (15-product-onboarding.md step 2): replacing app/agent.py's unconditional populate_mock_data() call gates all seeding.
Actual: init_database() (app/database/db.py:259-261) itself unconditionally calls populate_products() (22 fashion) and populate_retail_test_products() (6 retail) on every run — agent.py:112 invokes it before populate_mock_data(). DEMO_DATASET=none must also gate/relocate those two calls or the catalog is never empty.
Blast radius: doc 15 step 2 + its Validation item 1. Amended doc 15 in this branch with provenance.

## 2026-07-22 — DISCOVERY: ws08's "silent no-reference" finding is already half-fixed by ws09
Assumed (doc 15's ws08 amendment, 2026-07-19): generate_video_from_product silently proceeds with no warning when the reference image is missing.
Actual: ws09 (commit 20d7347) added result["warning"] = "No product image found …" (video_tools.py:730-736) when reference_image_used is False. Remaining live halves: routing both call sites through the storage seam, and list_products' unchecked URL emission.
Blast radius: doc 15's first ws08 amendment block. Amended with provenance so it doesn't read as unsolved.

## 2026-07-22 — DISCOVERY: the storage.googleapis.com surface is four tools across three files, not one
Assumed (doc 15 step 1 + ws08 amendment): the URL-emission sites are list_products and generate_video_from_product.
Actual: review_tools.get_video_review_table, review_tools.get_video_details, and maps_tools' location detail also emit get_public_url/get_video_public_url output (see research evidence) — all four surfaces must route through the seam per ws09's "never storage.googleapis.com links".
Blast radius: doc 15 step 1 scope. Amended with provenance.
## 2026-07-22 — checkpoint 2: working doc approved
Owner approved the six-dimension restatement ("Yes — approved, write the plan"). Drive-bundle logistics question resolved: hypothesis confirmed — this workstream ships download/verify/install code + a builder script verified against a locally built bundle; owner uploads the zip to their own Drive later and sets DEMO_ASSETS_DRIVE_ID; graceful "bundle not configured" skip until then. Working doc: working-doc.md (commit 436b8af).
