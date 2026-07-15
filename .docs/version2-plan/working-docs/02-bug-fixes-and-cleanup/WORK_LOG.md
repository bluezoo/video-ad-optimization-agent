# Work Log — Workstream 02: bug-fixes-and-cleanup

Append-only, newest at the bottom. Owned by the `tracking-workstream-progress` skill.

## 2026-07-14 19:29 — kickoff: worktree created
Branch `version_2_bug-fixes-and-cleanup` created off `version_2` (7d3c866, post-Phase-0 merge), worktree at `.claude/worktrees/version_2_bug-fixes-and-cleanup`. Base verified. STATUS.md row set to "kickoff in progress" in main checkout. Phase doc research: pending.

**Amended 2026-07-14 — phase doc research done.** All 9 items re-verified against current code; every claim holds. Highlights beyond the phase doc:
- Item 1: daily row dicts lack a raw `revenue` key (only date/impressions/dwell_time/circulation/revenue_per_impression), though raw revenue is computed inside the loop. Both bad defaults confirmed (metrics_tools.py `generate_metrics_visualization`, maps_tools.py `generate_map_visualization`).
- Item 2: `get_campaign_metrics` returns `summary=None` with `status="success"` whenever no rows have impressions (metrics_tools.py ~246) — the debug f-string `summary['total_impressions']` before the guard is a live `TypeError: 'NoneType' object is not subscriptable`.
- Item 5: `CAMPAIGN_CATEGORIES` (config.py:89) is **dead config** — zero consumers in app/ or tests/. DB CHECK (db.py:70) has 5 values incl. `holiday`; config has 4. `create_campaign` (campaign_tools.py ~66-73) never touches either — hardcoded product→campaign mapping with silent `"essentials"` fallback.
- Item 6: campaign 4 is `sage-satin-camisole` at The Grove (mock_data.py:63-64); stale texts confirmed at agent.py:152, 539 (Emerald Satin), agent.py:310 (90 days; mock data generates 30), agent.py:200 + video_tools.py:18 (Gemini 2.0 Flash Exp). README:66 BigQuery correction **already recorded** in SETUP_INSTRUCTIONS.md:81 — that bullet needs no new work.
- Item 7: identical broad `except ImportError: pytest.skip` + `except Exception: pytest.xfail` in all 6 integration tests (test_agents.py:65-69 et al.).
- Item 9: all 3 e2e failures reproduce on this branch (3 failed, 22 passed, 1 skipped). Root causes: `generate_video_from_product` is `async def` taking `variation: Optional[dict]` (test passes stale `model_ethnicity=`/`setting=`/etc. kwargs, no `product_id`, no await); chart/map tools are `async def` called sync → "coroutine is not iterable". Chart test also passes invalid `metric="rpi"`. pytest is `asyncio_mode = auto`, so async test fns just work. All 3 are `slow`-marked but `make test-e2e` runs without deselecting slow, so they fail on every e2e run.
- Worktree env set up: `app/.env` copied from main checkout, `.venv` built with python3.12, `google-adk[eval]` installed.
