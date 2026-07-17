# Workstream 05: deterministic-demo-data — WORK_LOG

Append-only. Newest at the bottom. See `tracking-workstream-progress`.

## 2026-07-17 — kickoff: worktree created; phase doc research done
Branch version_2_deterministic-demo-data off version_2 @ 1008c79 (post-replan; Phase 4 dependency merged as a29f182). Research (3 parallel readers: repo claims, donor generator, port corrections): all phase-doc claims CONFIRMED (±1 line drift on review_tools cites: def :455, calls :169/:564). Donor pinned at b6e3302 (feat/plan3-slice1-bq-mvp tip == HEAD; working tree dirty on mock_bigquery.py + 4 scripts, untouched — all reads via git show). Port corrections distilled from bluezoo-mapping-verification.md. Key findings for the working doc: donor seed.py is numpy+pandas (neither in app/requirements.txt); no screen entity exists in this repo (campaign IS the store binding); zero tests assert the old generators' RNG ranges/date direction; flat revenue=impressions×constant would make RPI identical across creatives (Phase 7 tension — flagged to owner).
