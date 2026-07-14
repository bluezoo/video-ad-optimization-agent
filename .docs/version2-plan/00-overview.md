# Version 2 Plan — Overview & Sequencing

> Supersedes nothing — `.docs/2026-07-12-version2-review-and-plan.md` is left untouched as historical record. This folder is the new guiding document, re-grounded against the actual codebase (as of 2026-07-13) and against BlueZoo's real API, product line, and public statements. Where this plan disagrees with the original, the disagreement is called out explicitly in "What changed vs. the original plan" below — nothing is silently dropped.

## Why this exists

The client asked for two things this weekend, in their own words (screenshots in `.docs/.context/IMG_2787.PNG`, `IMG_2808.PNG`):

1. **Generalize beyond fashion.** The demo currently hardcodes a fashion retailer end-to-end.
2. **Align the demo with BlueZoo's real data schema, and isolate live-vs-cached data-source code** so BlueZoo's actual sensor/PoS data can eventually be plugged in without a rewrite.

Both are legitimate, and both are in this plan. But the original planning doc, while directionally right, has three problems this rewrite fixes:

- **It missed something more urgent than either of the client's asks.** The app's current image and video models are already deprecated or about to be (see Phase 0 — this is the single most time-sensitive item in the whole plan, independent of everything else).
- **It over-assumed how hard some things would be**, before we'd actually read BlueZoo's API docs or the current codebase closely enough. Several "hard problems" turn out to be smaller than they looked; a couple of "small tweaks" turn out to need more care.
- **It was organized as 6 broad workstreams**, which is the right shape for a proposal but the wrong shape for execution — a "workstream" like "upgrade media generation" is really 4-5 independently testable steps. This rewrite breaks everything into phases small enough to pick up one at a time, each with its own goal, concrete steps, and a way to check it's actually done.

## Philosophy (per explicit instruction — do not overcomplicate)

- **The current app works.** It has limitations, not a broken foundation. Every phase below should look like "add a layer" or "fix a bug," never "rewrite the core."
- **Small, sequential, testable.** Every phase produces something you can run `make test-unit` (or a named command) against and see pass/fail. No phase should take more than a few focused sessions.
- **Lowest-effort-and-highest-value first.** Phases are ordered so early wins are fast and de-risk later, harder phases — not ordered by "importance" in the abstract.
- **No speculative abstraction.** Where the plan calls for an interface (e.g., a data-source provider), it's because two concrete callers already need it (demo + live), not because "we might need it someday."
- **Demo mode stays first-class.** Nothing in this plan makes the demo worse, slower, or dependent on live (BlueZoo/PoS) credentials. `APP_MODE=demo` (added in Phase 5) must remain the default. **Caveat found during Codex review, not yet resolved:** demo mode today is not actually zero-external-account — `app/storage.py:171` requires a real GCS bucket/client for product images and raises without one, and the primary video pipeline (`app/tools/video_tools.py:520`) reads product images through that path. Either narrow this promise to "no BlueZoo/PoS credentials required" or add a local-fixture asset provider before Phase 5's validation claims "zero external accounts" — tracked as open question 16.

## What changed vs. the original plan (read this before reading the phase docs)

These are corrections and new findings from re-grounding against BlueZoo's real API/docs and the current codebase. They matter because they change sequencing and scope, not just wording.

1. **New, urgent, independent finding — model deprecation.** `app/config.py:27-28` currently point at `gemini-3-pro-image-preview` (Stage 1 image) and `veo-3.1-generate-preview` (Stage 2 video). Both are preview IDs on the Vertex AI surface this repo deploys to (Cloud Run / Agent Engine), and preview models on that surface have short, hard cutoffs. This has nothing to do with the client's two requests, was not in the original plan at all, and is the cheapest, most time-critical fix available (change two config strings + confirm output still works). It is now **Phase 0**, ahead of everything else. See `01-emergency-model-currency-fix.md`.

2. **"Impressions" terminology needs far less reconciliation than the original plan assumed.** BlueZoo's own Data Warehouse API docs define `sensor_visits` as inner-zone visit counts, and literally caption them "also known as impressions." The metric glossary work (Phase 3) is now mostly "adopt BlueZoo's existing vocabulary," not "invent a mapping layer between two incompatible worldviews."

3. **`run_query` (BlueZoo's SQL-like data endpoint) is server-side SELECT-only** — no DML/DDL is possible through it. The original plan's implied injection/write-safety concerns for the live adapter are lower-risk than assumed; the adapter work (Phase 11) can focus on auth, pagination, and schema mapping rather than a query-sanitization layer.

4. **Media-model positioning needed correcting, but not in the direction first assumed.** The original plan treated Gemini Omni Flash as a "fast draft" tier with Veo as the finish line for "final 4K" output. That framing is wrong, but so was this plan's first-draft correction of it. **Codex review correction:** Google's own primary sources (the Interactions API reference and the `python-genai` repo) currently label the Interactions API **experimental / `v1beta1`**, and Omni Flash's own model page calls it **public preview**, describing price/performance and conversational editing — not a stated default replacement for Veo. Phase 13b is corrected accordingly: Omni Flash is an **optional, experimental backend to evaluate**, not a GA default. Veo 3.1 (GA after Phase 0) remains the default until a real side-by-side evaluation says otherwise.

5. **Two independently-drifted mock-metrics generators exist today**, producing inconsistent numbers for the same demo: `app/database/mock_data.py:168-235` (`revenue_per_impression = random.uniform(0.02, 0.08)`) vs. `app/tools/review_tools.py:454-513` (a **separate** function, RPI $0.08-$0.15, impressions 800-1500). This is a concrete, low-effort, high-visibility bug (numbers don't match depending which code path generated them) — it's in Phase 4, ahead of any BlueZoo integration work.

6. **`get_campaign_locations` in `app/tools/maps_tools.py` reads from legacy/abandoned tables** (`campaign_ads`, `campaign_metrics`) instead of the current schema (`campaign_videos`, `video_metrics`), so it silently returns incomplete data today. Folded into Phase 1 (bug cleanup) rather than left as an undocumented landmine.

7. **BlueZoo has already publicly announced and open-sourced a very similar project**: `github.com/bluezoo/ad-campaign-agent` (press release dated 2026-06-17), naming both the client and this repo's other maintainer, and referencing "Gemini Omni" and BigQuery. This repo's relationship to that public repo is an **open question for the client**, not something this plan can resolve unilaterally — see `99-open-questions.md`, item 1. It directly affects whether Phase 11 targets BlueZoo's REST API (`api.bluezoo.io`, confirmed to exist and documented) or a BigQuery dataset-share (mentioned in the press release and this repo's own README, but not yet confirmed as the intended integration path).

8. **RPI (revenue-per-impression) is BlueZoo's own coined/marketed term**, not something this app invented — confirmed via a direct the client quote in BlueZoo's own materials. The "RPI across creatives" comparison the client asked about is squarely BlueZoo's flagship business metric, which is why it's pulled forward to Phase 7 (right after the metrics groundwork), instead of being bundled deep inside a larger analytics workstream.

9. Several stale/inconsistent facts embedded directly in agent instructions and docs — hardcoded "fashion retail company" framing in all 5 agent instructions (`app/agent.py`), a stale "Emerald Satin Slip Dress" reference vs. the actual current mock product (`sage-satin-camisole`), a stale "90 days" claim vs. the actual 30-day mock window, and a stale claim that Stage 1 uses "Gemini 2.0 Flash Exp" when `config.py` actually configures `gemini-3-pro-image-preview` — are folded into Phase 1 (cheap, mechanical, zero architectural risk) rather than deferred to the generalization phase.

10. **BlueZoo's real historical visit data has a 15-minute grain, not per-minute** — confirmed directly against the API docs during Codex's review pass. The first draft of Phases 9-10 assumed a per-minute synthetic time series and a simplistic `[start_time, end_time) → int` join, which doesn't match BlueZoo's actual data shape and doesn't solve the real problem: this app's video creatives currently default to 8 seconds (`app/config.py:30`), so dozens of rotating creatives can fall inside a single 15-minute sensor window. Phases 9 and 10 (below) are corrected to use 15-minute buckets and to treat "how do we attribute one sensor window's visits across multiple rotating creatives" as an explicit open question for the client, not an implementation detail.
11. **A full adversarial review pass (Codex/GPT-5.6, extra-high effort) was run against this plan and the live codebase before treating it as final.** Findings are preserved at `CODEX-REVIEW.md` in this folder. Every phase doc below has already been corrected for that review's "blocking" and "should-fix" findings — file:line claims that were stale or wrong, sequencing/dependency errors, over-complication flags, and unverified-vs-verified external claims (especially around the Interactions API's actual GA status, corrected in item 4). Read `CODEX-REVIEW.md` alongside this doc if you want the full trail of what was caught and fixed, rather than just the corrected end state.
12. **The client sent a concrete architecture proposal for ad-play tracking after this plan's first draft was reviewed** (email transcribed in `.docs/.context/project_context.md`). It specified an exact input schema — sensor/screen identifier (linking to BlueZoo's data warehouse), ad_name, product identifiers (linking to the retailer's PoS data warehouse), and a start/end time window — sourced from the retailer's **content management system (CMS)**, delivered on a **batch, end-of-day cadence** (not real-time). For each such ad-play record, the design is: call BlueZoo's API for impressions using the screen + time window, and call the retailer's PoS system for revenue using the product identifier(s). This is good news for the plan's simplicity goal — it's a batch reconciliation job, not a real-time stream — and it substantially resolves several open questions that were previously flagged as blocking design decisions rather than confirmed direction. Phases 9, 10, and 11 (below) and the open-questions list are updated accordingly. It also introduces a **third external system this app needs an input contract for** (the CMS/ad-play feed), alongside BlueZoo (audience) and the PoS system (revenue) — folded into Phase 9 rather than given its own phase, since Phase 9 already owns the playout/ad-play entity.

None of this changes the client's two core asks or the eventual destination. It changes what happens first and removes some imagined complexity.

## Grounding sources (so nothing below is asserted from memory)

- Current codebase: `app/agent.py`, `app/config.py`, `app/database/db.py`, `app/database/mock_data.py`, `app/tools/metrics_tools.py`, `app/tools/prompt_builders.py`, `app/tools/video_tools.py`, `app/tools/review_tools.py`, `app/tools/campaign_tools.py`, `app/tools/maps_tools.py`, `app/models/variation.py`, `app/storage.py`, `app/requirements.txt`, `scripts/deploy.sh`, `scripts/deploy_ae.sh`, `README.md` — all read directly, file:line citations throughout the phase docs.
- BlueZoo Data Warehouse & Real-time API docs: `https://api.bluezoo.io/#89e2277d-43ef-424b-b4d6-6f473538f108` — fetched and parsed directly (table schemas, auth headers, `run_query` semantics).
- BlueZoo product/business context: `https://www.bluezoo.io/products/` and related pages — fetched directly.
- BlueZoo's public GitHub repo and press release (`github.com/bluezoo/ad-campaign-agent`, 2026-06-17) — found via research, referenced as an open question, not assumed.
- Gemini/Veo model status: Vertex AI model garden / release-notes pages, `google-genai` SDK docs (current version 2.11.0, 2026-07-09) — fetched directly to confirm deprecation dates and the Interactions API surface.
- ADK best practices (toolsets, session state scoping, HITL/tool confirmation, Secret Manager integration, durable session services): official ADK docs via `google-dev-knowledge` MCP. **Correction from Codex review:** this checkout has no installed `google-adk`/`google-genai` environment and no lockfile (`app/requirements.txt` specifies unpinned lower bounds only) — so these were checked against official docs, not against "installed version behavior" as an earlier draft of this doc overstated. Any phase that depends on a specific ADK primitive/version (Secret Manager client, Tool Confirmation) needs a short implementation-time spike against a pinned version before being treated as settled — flagged explicitly in Phase 12.

## Phase sequencing

Each phase has its own file with Goal / Current State / Steps / Validation / Exit Criteria / Dependencies. Work through them in order — later phases assume earlier ones are done. Phases marked "independent" can be pulled forward or done in parallel with anything above them if there's spare capacity.

| Phase | File | What it does | Effort | Depends on |
|---|---|---|---|---|
| 0 | `01-emergency-model-currency-fix.md` | Swap deprecated preview model IDs for GA replacements | Trivial (~1 hr) | none — do this today |
| 1 | `02-bug-fixes-and-cleanup.md` | Fix live bugs + stale text (chart tool defaults/null-deref, maps legacy tables, config/schema drift, stale instructions) | Small | none |
| 2 | `03-metrics-glossary-and-terminology.md` | Write down BlueZoo-aligned definitions of impressions/RPI/revenue/dwell as the single source of truth | Small | none |
| 3 | `04-centralize-rpi-metrics.md` | Collapse the independent RPI/metric computations (including the weekly ratio-of-sums fix) into one shared function | Medium | Phase 2 |
| 4 | `05-deterministic-demo-data.md` | Replace the drifted random-metric generators (3 call sites) with one deterministic generator | Small | Phase 3 |
| 5 | `06-app-mode-config-skeleton.md` | Add a typed `APP_MODE=demo\|connected` config value | Small | none (independent of 2-4, sequenced here for convenience) |
| 6 | `07-rpi-across-creatives-chart.md` | Ship the RPI-across-creatives comparison view the client asked about, as real deterministic data (not AI-rendered) | Medium | Phases 3, 4 |
| 7 | `08-product-schema-generalization.md` | Typed, vertical-agnostic product persistence + retrieval adapter; additive DB migration | Medium | Phase 1 |
| 8 | `09-prompt-and-agent-generalization.md` | De-hardcode prompts/instructions/tool defaults from "fashion" to the generic envelope; proves end-to-end non-fashion generation | Medium | Phase 7 |
| 9 | `10-playout-attribution.md` | Synthetic, BlueZoo-shaped (15-minute grain) playback log + screen×video×time attribution, demo-only | Medium | Phases 3, 4, 7; cross-creative attribution rule (open question 17) needed before the join logic is finalized |
| 10 | `11-live-bluezoo-adapter.md` | Real BlueZoo Data Warehouse/Real-time API adapter (with a cached-fixture variant too) behind `APP_MODE=connected` | Large | Phases 5, 9; blocked on open questions 1, 2 (repo/integration-path) and informed by 11, 12 |
| 11 | `12-live-pos-adapter.md` | Real revenue/PoS adapter behind `APP_MODE=connected` | Large | Phases 3, 5, 10; blocked on open questions 3, 4 |
| 12 | `13-production-hardening-live-mode.md` | Auth, signed URLs, identity-backed audit trail — the connected-mode launch gate (minimum live-secret handling moves into Phases 10/11 themselves, see those docs) | Medium | Phases 10, 11 |
| 13a | `14a-image-model-upgrade-nano-banana.md` | Config-driven image model swap + evaluate Nano Banana 2 Lite | Medium | Phase 0 (decoupled from everything else) |
| 13b | `14b-video-model-upgrade-omni-flash.md` | Evaluate Gemini Omni Flash (experimental Interactions API) as an optional second video backend | Large | Phase 0, ideally after 13a |

Phases 13a/13b are intentionally decoupled — they can run any time after Phase 0 without waiting on the generalization or live-mode track, exactly as in the original plan's Phase 9a/9b split (that part of the original sequencing was correct and is kept). Note Phase 7's exit criterion is deliberately narrower than "full non-fashion video generation" — proving a non-fashion product survives image/video generation end-to-end is Phase 8's job, since Phase 7 alone can't touch prompt construction.

## Open questions

Every phase doc lists its own open questions inline. They're also consolidated in `99-open-questions.md` so they can be sent to BlueZoo as a single list without digging through 14 files.

## How to use this with an implementation model (Sonnet, etc.)

Hand one phase file at a time to the implementation model, in order. Each phase doc is self-contained: it names exact files/functions, explains why, and defines a pass/fail test. Do not skip ahead — later phases assume the file:line references from earlier phases have already changed (e.g., Phase 3 assumes Phase 2's glossary constants exist).
