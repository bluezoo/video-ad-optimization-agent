# RPI-Across-Creatives Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A creative-level RPI comparison (`compare_creatives_within_campaign()`) plus a deterministic matplotlib chart tool, wired into the Analytics Agent — with Option A per-creative RPI variance in the demo derivation layer so the comparison is real.

**Architecture:** Option A adds a seeded `video_rpi()` factor in `app/demo_data/derive.py` (the disposable layer Phase 10 replaces). The comparison function is a new metrics tool using the existing per-video aggregation pattern; the chart tool calls it, renders with matplotlib `Figure` + `FigureCanvasAgg` (no pyplot, headless-safe) to an in-memory PNG, and saves via the existing ToolContext artifact contract.

**Tech Stack:** matplotlib (new dep, both requirement lists), numpy (already a dep; fixing its ws05 omission from the Agent Engine deploy list), pytest (asyncio_mode=auto; first ToolContext mock in the suite).

## Global Constraints

- **Option A exactly (owner decision 2026-07-19):** `video_rpi(ad_campaign_id, video_id) = round(DEMO_RPI * (0.6 + seeded_uniform * 0.8), 4)`, seeded via the existing `_seeded_rng("rpi", ad_campaign_id, video_id)` pattern → band [0.03, 0.07], **constant across days**. No per-day jitter (Option C rejected). `DEMO_RPI` stays the single base constant — never a second revenue constant.
- **No-discontinuity invariant:** the factor is keyed only by (campaign, video), absolute, never normalized across a campaign's videos — `test_later_activation_never_changes_existing_rows` must pass unchanged.
- **RPI is ratio-of-sums** (docs/METRICS.md): aggregate per-video revenue/impressions first, then ONE `compute_rpi()` call per video (`app/tools/metrics_shared.py:14`, `compute_rpi(total_revenue, total_impressions)`). Never average daily ratios.
- **All-time window:** `compare_creatives_within_campaign` uses NO days filter — SQLite `date('now', …)` filters can drift past the demo anchor window and silently exclude rows.
- **Artifact contract** (copy from `generate_metrics_visualization`, `app/tools/metrics_tools.py:1073-1089`): async tool, trailing `tool_context: ToolContext = None`, `types.Part.from_bytes(data=…, mime_type="image/png")`, `await tool_context.save_artifact(filename=…, artifact=…)`, graceful `tool_context is None` branch, return metadata + structured data, never bytes.
- **matplotlib usage:** `matplotlib.figure.Figure` + `matplotlib.backends.backend_agg.FigureCanvasAgg` directly — never `pyplot` (global state in an async server). 16:9: `figsize=(12.8, 7.2), dpi=100`. Render to `io.BytesIO`, never a file on disk.
- **Do NOT touch:** `generate_metrics_visualization`, `CHART_TEMPLATES`, `app/demo_data/seed.py`, DB schema, README.md, DEMO_GUIDE.md.
- Include zero-metric activated videos in the comparison with zeroed metrics (RPI 0.0 via `compute_rpi`) — never silently drop them (the `get_top_performing_ads` HAVING clause is the anti-pattern).
- No AI-attribution trailers in commit messages.
- The PostToolUse hook runs `make test-unit` after `app/**/*.py` edits — matplotlib is already installed in this worktree's `.venv` (controller pre-installed); keep each file edit complete.

---

### Task 1: Option A — per-creative RPI factor in the derivation layer

**Files:**
- Modify: `app/demo_data/derive.py` (new `video_rpi()` after `video_fraction()` ~line 58; revenue line ~line 94; two docstring lines)
- Modify: `app/demo_data/constants.py` (docstring)
- Test: `tests/unit/test_demo_derive.py` (replace `test_revenue_is_flat_demo_rpi`; add three tests)

**Interfaces:**
- Produces: `app.demo_data.derive.video_rpi(ad_campaign_id: int, video_id) -> float` (Task 2's tests and Scenario docs reference the [0.03, 0.07] band; Task 4's scenario criteria rely on per-creative-constant ratios).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_demo_derive.py`: add `video_rpi` to the existing `from app.demo_data.derive import …` block, then REPLACE the whole `test_revenue_is_flat_demo_rpi` method with these four (same class, same indentation):

```python
    def test_revenue_uses_per_creative_rpi(self):
        rows = derive_video_metrics_rows(CID, [101, 102], D_FROM, D_TO)
        for r in rows:
            assert r["revenue"] == round(r["impressions"] * video_rpi(CID, r["video_id"]), 2)

    def test_video_rpi_band_and_determinism(self):
        for vid in (101, 102, 999):
            factor = video_rpi(CID, vid)
            assert 0.03 <= factor <= 0.07
            assert factor == video_rpi(CID, vid)

    def test_video_rpi_differs_across_creatives(self):
        assert video_rpi(CID, 101) != video_rpi(CID, 102)

    def test_window_rpi_matches_creative_constant(self):
        rows = derive_video_metrics_rows(CID, [101], D_FROM, D_TO)
        total_rev = sum(r["revenue"] for r in rows)
        total_imp = sum(r["impressions"] for r in rows)
        assert abs(compute_rpi(total_rev, total_imp) - video_rpi(CID, 101)) < 0.001
```

(`CID`, `D_FROM`, `D_TO`, `compute_rpi`, `derive_video_metrics_rows` already exist in this file — reuse them; if `DEMO_RPI` becomes unused in the import block after the replacement, remove it from the imports.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_demo_derive.py -v`
Expected: the four new tests fail with `ImportError`/`AttributeError` on `video_rpi`; the rest pass.

- [ ] **Step 3: Implement in `app/demo_data/derive.py`**

Insert after `video_fraction()` (after its closing `return`, ~line 58):

```python
def video_rpi(ad_campaign_id: int, video_id) -> float:
    """Deterministic per-(campaign, video) RPI in [0.03, 0.07].

    DEMO_RPI x a seeded factor in [0.6, 1.4], constant across days: each
    creative's revenue/impressions ratio stays ONE checkable constant, but
    creatives differ from each other (Phase 7 owner decision, reversing the
    ws05 strict-flat choice). Keyed per (campaign, video) only — absolute,
    so later activations never change existing videos' rows."""
    rng = _seeded_rng("rpi", ad_campaign_id, video_id)
    return float(round(DEMO_RPI * (0.6 + rng.uniform() * 0.8), 4))
```

In `derive_video_metrics_rows`: beside the existing `fraction = video_fraction(ad_campaign_id, video_id)` line add `rpi = video_rpi(ad_campaign_id, video_id)`, and change the revenue entry to:

```python
                    "revenue": round(impressions * rpi, 2),
```

Update the function docstring line `revenue = impressions x DEMO_RPI (flat, owner decision).` to:

```
    revenue = impressions x video_rpi(campaign, video) — deterministic
    per-creative RPI in [0.03, 0.07] (Phase 7 owner decision; was flat 0.05).
```

- [ ] **Step 4: Update `app/demo_data/constants.py` docstring**

Replace the docstring sentence claiming demo RPI is identical across creatives (lines ~6-8, wording: "demo RPI is identical across creatives until Phase 7 revisits") with:

```
DEMO_RPI is the demo BASE rate: Phase 7 multiplies it by a deterministic
per-(campaign, video) factor in [0.6, 1.4] (see derive.video_rpi), so each
creative has its own stable RPI in [0.03, 0.07]. Still the single canonical
constant — never duplicate it.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_demo_derive.py tests/unit/test_demo_seed.py tests/unit/test_demo_meta.py tests/unit/test_review_tools.py -v`
Expected: all pass — including the untouched no-discontinuity and determinism tests.

- [ ] **Step 6: Lint + unit suite**

Run: `.venv/bin/ruff check app/demo_data/ tests/unit/test_demo_derive.py` → no new errors.
Run: `make test-unit` → all pass.

- [ ] **Step 7: Commit**

```bash
git add app/demo_data/derive.py app/demo_data/constants.py tests/unit/test_demo_derive.py
git commit -m "Add deterministic per-creative RPI factor to demo derivation (Phase 7 owner decision)"
```

---

### Task 2: `compare_creatives_within_campaign()` metrics tool

**Files:**
- Modify: `app/tools/metrics_tools.py` (new function after `compare_campaigns`, before the CHART section around line 765)
- Test: `tests/unit/test_metrics_tools.py` (new class after `TestCompareCampaigns`)

**Interfaces:**
- Consumes: `compute_rpi` (already imported at `metrics_tools.py:26`), `get_db_cursor`, `json` (imported).
- Produces: `compare_creatives_within_campaign(campaign_id: int) -> dict` returning `{status, campaign_id, campaign_name, creatives_compared, creatives: [{video_id, video_filename, variation_name, characteristics, metrics: {total_impressions, total_revenue, average_dwell_time, revenue_per_impression}, rpi_rank}], best_performer: {video_id, variation_name, revenue_per_impression}, note}` — Task 3's chart tool calls this and embeds the full payload under `"comparison"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_metrics_tools.py`:

```python
class TestCompareCreativesWithinCampaign:
    """Creative-level comparison (Phase 7)."""

    def test_ranks_by_rpi_not_revenue(self, test_db):
        from app.tools.metrics_tools import compare_creatives_within_campaign

        # video 0: high volume, low ratio; video 1: low volume, high ratio
        made = _make_campaign_with_metrics(
            [
                {"metric_date": "2026-07-01", "impressions": 10000, "revenue": 300.0, "video_index": 0},
                {"metric_date": "2026-07-01", "impressions": 1000, "revenue": 60.0, "video_index": 1},
            ],
            num_videos=2,
        )
        result = compare_creatives_within_campaign(made["campaign_id"])
        assert result["status"] == "success"
        assert result["creatives_compared"] == 2
        top = result["creatives"][0]
        assert top["video_id"] == made["video_ids"][1]  # 0.06 beats 0.03
        assert top["rpi_rank"] == 1
        assert top["metrics"]["revenue_per_impression"] == 0.06
        assert result["best_performer"]["video_id"] == made["video_ids"][1]

    def test_rpi_is_ratio_of_sums_via_compute_rpi(self, test_db):
        from app.tools.metrics_shared import compute_rpi
        from app.tools.metrics_tools import compare_creatives_within_campaign

        made = _make_campaign_with_metrics(
            [
                {"metric_date": "2026-07-01", "impressions": 100, "revenue": 9.0},
                {"metric_date": "2026-07-02", "impressions": 300, "revenue": 3.0},
            ]
        )
        result = compare_creatives_within_campaign(made["campaign_id"])
        c = result["creatives"][0]
        assert c["metrics"]["revenue_per_impression"] == compute_rpi(12.0, 400)  # 0.03, not mean(0.09, 0.01)

    def test_zero_metric_activated_video_included(self, test_db):
        from app.tools.metrics_tools import compare_creatives_within_campaign

        made = _make_campaign_with_metrics(
            [{"metric_date": "2026-07-01", "impressions": 500, "revenue": 25.0, "video_index": 0}],
            num_videos=2,  # video 1 activated but has zero metric rows
        )
        result = compare_creatives_within_campaign(made["campaign_id"])
        assert result["creatives_compared"] == 2
        zero = [c for c in result["creatives"] if c["video_id"] == made["video_ids"][1]][0]
        assert zero["metrics"]["total_impressions"] == 0
        assert zero["metrics"]["revenue_per_impression"] == 0.0

    def test_campaign_not_found(self, test_db):
        from app.tools.metrics_tools import compare_creatives_within_campaign

        result = compare_creatives_within_campaign(999999)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_no_activated_videos(self, test_db):
        from app.tools.campaign_tools import create_campaign
        from app.tools.metrics_tools import compare_creatives_within_campaign

        created = create_campaign(product_id=1, store_name="No Videos Store", city="Austin", state="TX")
        result = compare_creatives_within_campaign(created["campaign"]["id"])
        assert result["status"] == "error"
        assert "activated" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py::TestCompareCreativesWithinCampaign -v`
Expected: 5 failures, `ImportError: cannot import name 'compare_creatives_within_campaign'`.

- [ ] **Step 3: Implement in `app/tools/metrics_tools.py`**

Insert after `compare_campaigns` ends (before the `# ===` CHART GENERATION section header, ~line 765):

```python
def compare_creatives_within_campaign(campaign_id: int) -> dict:
    """Compare all activated creatives (video variations) within ONE campaign.

    Creative-level counterpart to compare_campaigns() (which compares whole
    campaigns): returns, per activated video, all-time totals and RPI via
    compute_rpi() (ratio of sums — see docs/METRICS.md), plus variation
    metadata so the comparison is legible. All-time window by design: demo
    metrics live in a fixed anchor window that date('now') filters can
    silently drift past.

    Args:
        campaign_id: The campaign whose creatives to compare

    Returns:
        Dictionary with per-creative metrics ranked by RPI
    """
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name FROM campaigns WHERE id = ?", (campaign_id,))
        campaign = cursor.fetchone()
        if not campaign:
            return {"status": "error", "message": f"Campaign {campaign_id} not found"}

        cursor.execute('''
            SELECT
                cv.id AS video_id,
                cv.video_filename,
                cv.variation_name,
                cv.variation_params,
                SUM(vm.revenue) AS total_revenue,
                SUM(vm.impressions) AS total_impressions,
                AVG(vm.dwell_time_seconds) AS avg_dwell
            FROM campaign_videos cv
            LEFT JOIN video_metrics vm ON cv.id = vm.video_id
            WHERE cv.campaign_id = ? AND cv.status = 'activated'
            GROUP BY cv.id
        ''', (campaign_id,))
        rows = cursor.fetchall()

    if not rows:
        return {
            "status": "error",
            "message": (
                f"Campaign {campaign_id} has no activated videos to compare. "
                "Use the Review Agent to activate videos first."
            ),
        }

    creatives = []
    for row in rows:
        characteristics = {}
        if row["variation_params"]:
            try:
                params = json.loads(row["variation_params"])
                characteristics = {
                    key: params.get(key)
                    for key in ("setting", "mood", "model_ethnicity", "lighting", "time_of_day")
                    if params.get(key)
                }
            except json.JSONDecodeError:
                pass
        total_revenue = round(row["total_revenue"] or 0.0, 2)
        total_impressions = int(row["total_impressions"] or 0)
        creatives.append({
            "video_id": row["video_id"],
            "video_filename": row["video_filename"],
            "variation_name": row["variation_name"] or "default",
            "characteristics": characteristics,
            "metrics": {
                "total_impressions": total_impressions,
                "total_revenue": total_revenue,
                "average_dwell_time": round(row["avg_dwell"], 1) if row["avg_dwell"] else 0.0,
                "revenue_per_impression": compute_rpi(total_revenue, total_impressions),
            },
        })

    creatives.sort(key=lambda c: c["metrics"]["revenue_per_impression"], reverse=True)
    for rank, creative in enumerate(creatives, start=1):
        creative["rpi_rank"] = rank

    best = creatives[0]
    return {
        "status": "success",
        "campaign_id": campaign_id,
        "campaign_name": campaign["name"],
        "creatives_compared": len(creatives),
        "creatives": creatives,
        "best_performer": {
            "video_id": best["video_id"],
            "variation_name": best["variation_name"],
            "revenue_per_impression": best["metrics"]["revenue_per_impression"],
        },
        "note": "RPI per creative = compute_rpi() over all-time sums (ratio of sums, never sum of ratios).",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py -v`
Expected: all pass (new class 5/5, existing classes untouched).

- [ ] **Step 5: Lint + unit suite**

Run: `.venv/bin/ruff check app/tools/metrics_tools.py tests/unit/test_metrics_tools.py` → no NEW errors (7 pre-existing errors in this file are out of scope — compare against `git stash`-free baseline by checking the flagged lines are not yours).
Run: `make test-unit` → all pass.

- [ ] **Step 6: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py
git commit -m "Add compare_creatives_within_campaign metrics tool"
```

---

### Task 3: Deterministic matplotlib chart tool + dependency wiring

**Files:**
- Modify: `app/tools/metrics_tools.py` (imports + new async tool after `compare_creatives_within_campaign`)
- Modify: `app/requirements.txt` (matplotlib under Feature Dependencies)
- Modify: `scripts/deploy_ae_inline.py` (requirements list ~lines 291-298: add matplotlib AND the missing numpy — ws05 DISCOVERY fix)
- Test: `tests/unit/test_metrics_tools.py` (new class)

**Interfaces:**
- Consumes: `compare_creatives_within_campaign` (Task 2, exact return shape above); existing `types`, `time`, `ToolContext` imports in metrics_tools.py.
- Produces: `async generate_creative_comparison_chart(campaign_id: int, tool_context: ToolContext = None) -> dict` returning `{status, message, chart: {filename, artifact_saved, artifact_version, chart_data: {labels, rpi_values}}, comparison: <full Task-2 payload>}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_metrics_tools.py`:

```python
class TestGenerateCreativeComparisonChart:
    """Deterministic matplotlib chart (Phase 7) — no AI image model, no slow marker."""

    async def test_chart_data_matches_comparison_return(self, test_db):
        from app.tools.metrics_tools import generate_creative_comparison_chart

        made = _make_campaign_with_metrics(
            [
                {"metric_date": "2026-07-01", "impressions": 10000, "revenue": 300.0, "video_index": 0},
                {"metric_date": "2026-07-01", "impressions": 1000, "revenue": 60.0, "video_index": 1},
            ],
            num_videos=2,
        )
        result = await generate_creative_comparison_chart(made["campaign_id"])
        assert result["status"] == "success"
        comp = result["comparison"]
        assert result["chart"]["chart_data"]["labels"] == [
            c["variation_name"] for c in comp["creatives"]
        ]
        assert result["chart"]["chart_data"]["rpi_values"] == [
            c["metrics"]["revenue_per_impression"] for c in comp["creatives"]
        ]
        assert result["chart"]["artifact_saved"] is False  # no tool_context

    async def test_artifact_saved_with_tool_context(self, test_db):
        from unittest.mock import AsyncMock, MagicMock

        from app.tools.metrics_tools import generate_creative_comparison_chart

        made = _make_campaign_with_metrics(
            [{"metric_date": "2026-07-01", "impressions": 500, "revenue": 25.0}]
        )
        ctx = MagicMock()
        ctx.save_artifact = AsyncMock(return_value=1)
        result = await generate_creative_comparison_chart(made["campaign_id"], tool_context=ctx)
        assert result["chart"]["artifact_saved"] is True
        assert result["chart"]["artifact_version"] == 1
        ctx.save_artifact.assert_awaited_once()
        artifact = ctx.save_artifact.await_args.kwargs["artifact"]
        assert artifact.inline_data.mime_type == "image/png"
        assert artifact.inline_data.data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
        filename = ctx.save_artifact.await_args.kwargs["filename"]
        assert filename.startswith(f"creative_comparison_{made['campaign_id']}_")
        assert filename.endswith(".png")

    async def test_error_passthrough_for_missing_campaign(self, test_db):
        from app.tools.metrics_tools import generate_creative_comparison_chart

        result = await generate_creative_comparison_chart(999999)
        assert result["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py::TestGenerateCreativeComparisonChart -v`
Expected: 3 failures, `ImportError: cannot import name 'generate_creative_comparison_chart'`.

- [ ] **Step 3: Dependencies first**

`app/requirements.txt` — under `# =============================================================================\n# Feature Dependencies` after the numpy entry, add:

```
# Deterministic chart rendering (app/tools/metrics_tools.py creative comparison)
matplotlib>=3.8.0
```

`scripts/deploy_ae_inline.py` — in the requirements list (~lines 291-298), after `"Pillow>=10.2.0",` add BOTH (numpy is the ws05 omission fix — Agent Engine repopulates mock data at startup, which imports numpy via app/demo_data/seed.py):

```python
            "numpy>=1.26.0",
            "matplotlib>=3.8.0",
```

- [ ] **Step 4: Implement the tool in `app/tools/metrics_tools.py`**

Add to the module imports (top of file, stdlib group): `from io import BytesIO`. Add after the `from google.genai import types` group:

```python
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
```

(Deliberately NOT pyplot — Figure + Agg canvas has no global state and needs no backend switching in the async server.)

Insert after `compare_creatives_within_campaign`:

```python
async def generate_creative_comparison_chart(
    campaign_id: int,
    tool_context: ToolContext = None
) -> dict:
    """Render a deterministic RPI-per-creative bar chart for one campaign.

    Unlike generate_metrics_visualization (AI-image-drawn), this renders with
    matplotlib, so bar heights are exactly the numbers returned — the chart
    and the structured data come from the same compare_creatives_within_campaign()
    call. Saved as a PNG artifact for the web UI; also returns the full
    comparison payload.

    Args:
        campaign_id: The campaign whose activated creatives to chart
        tool_context: ADK tool context for artifact saving

    Returns:
        Dictionary with chart artifact metadata and the comparison data
    """
    comparison = compare_creatives_within_campaign(campaign_id)
    if comparison["status"] != "success":
        return comparison

    creatives = comparison["creatives"]
    labels = [c["variation_name"] for c in creatives]
    rpi_values = [c["metrics"]["revenue_per_impression"] for c in creatives]

    # 16:9 to match the repo's chart convention (CHART_TEMPLATES enforce it)
    fig = Figure(figsize=(12.8, 7.2), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    bars = ax.bar(labels, rpi_values, color="#4C7DE0")
    ax.set_title(f"RPI by creative — {comparison['campaign_name']}")
    ax.set_ylabel("Revenue per impression ($)")
    ax.bar_label(bars, fmt="$%.4f")
    ax.tick_params(axis="x", labelrotation=15)
    fig.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    image_bytes = buffer.getvalue()

    timestamp = int(time.time())
    filename = f"creative_comparison_{campaign_id}_{timestamp}.png"
    if tool_context:
        image_artifact = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        version = await tool_context.save_artifact(filename=filename, artifact=image_artifact)
        artifact_saved = True
    else:
        artifact_saved = False
        version = None

    return {
        "status": "success",
        "message": f"Creative comparison chart generated for campaign {campaign_id}",
        "chart": {
            "filename": filename,
            "artifact_saved": artifact_saved,
            "artifact_version": version,
            "chart_data": {"labels": labels, "rpi_values": rpi_values},
        },
        "comparison": comparison,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_metrics_tools.py -v`
Expected: all pass (3 new async tests run without markers — asyncio_mode=auto).

- [ ] **Step 6: Lint + unit suite + AST check on the deploy script**

Run: `.venv/bin/ruff check app/tools/metrics_tools.py tests/unit/test_metrics_tools.py` → no NEW errors.
Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/deploy_ae_inline.py').read()); print('parses OK')"` → `parses OK`.
Run: `make test-unit` → all pass.

- [ ] **Step 7: Commit**

```bash
git add app/tools/metrics_tools.py tests/unit/test_metrics_tools.py app/requirements.txt scripts/deploy_ae_inline.py
git commit -m "Add deterministic matplotlib creative-comparison chart tool; wire matplotlib + missing numpy into AE deploy"
```

---

### Task 4: Analytics Agent wiring, scenario updates, provenance amendments

**Files:**
- Modify: `app/agent.py` (import block for metrics tools; tool list at ~:370; `ANALYTICS_AGENT_INSTRUCTION` at ~:289-363)
- Modify: `docs/demo-scenarios/fashion.md` (F3.2 pass criteria; new Scenario F4)
- Modify: `.docs/version2-plan/07-rpi-across-creatives-chart.md` (resolution provenance note under the ws05 amendment)

**Interfaces:**
- Consumes: both Task 2/3 function names, exactly: `compare_creatives_within_campaign`, `generate_creative_comparison_chart`.

- [ ] **Step 1: Wire the tools in `app/agent.py`**

Add both names to the existing `from .tools.metrics_tools import (…)` import block (alphabetical position within the block). In the `analytics_agent` tool list (~:370), after `compare_campaigns,` add `compare_creatives_within_campaign,` and after `generate_metrics_visualization,` add `generate_creative_comparison_chart,`.

- [ ] **Step 2: Extend `ANALYTICS_AGENT_INSTRUCTION`**

After the `## Chart Visualization Capabilities` section, insert:

```
## Creative Comparison (RPI across creatives) — NEW
When the user asks which creative/video/variation is winning WITHIN one campaign:
- compare_creatives_within_campaign(campaign_id) - per-creative RPI (the primary KPI),
  impressions, revenue, dwell time, and variation characteristics, ranked by RPI
- generate_creative_comparison_chart(campaign_id) - deterministic bar chart of RPI per
  creative (rendered from the exact same numbers, not AI-drawn), saved as an artifact;
  also returns the full comparison data
Use compare_campaigns only for comparing WHOLE campaigns against each other;
use these two for creatives inside a single campaign.
```

In `## Response Guidelines`, add one numbered/bulleted line in the existing style: `- "Which creative/variation is winning in campaign X" → compare_creatives_within_campaign (add generate_creative_comparison_chart when a visual is asked for or helpful)`.

- [ ] **Step 3: Update Scenario F3.2 pass criteria in `docs/demo-scenarios/fashion.md`**

Replace F3.2's "Pass criteria" block (currently asserting every ratio == 0.05) with:

```
**Pass criteria (the workstream-05/07 assertion — check the arithmetic, don't
trust prose):**
- For every ad row reported: `revenue ≈ impressions × its reported RPI`
  (within cent rounding), and that RPI lies within [0.03, 0.07] (per-creative
  deterministic band — workstream 07 replaced the flat 0.05 with a seeded
  per-creative constant).
- In a multi-creative campaign, the reported RPIs are NOT all identical
  (at least two distinct values) — all-identical ratios would mean the
  per-creative factor regressed to flat.
- Impressions are non-zero for the activated video.
- FAIL if any row's revenue/impressions ratio disagrees with its own reported
  RPI beyond rounding — that would mean a non-deterministic or legacy
  generator path survived.
```

Also update the Scenario F3 intro line ("revenue = impressions × 0.05, so RPI is exactly 0.05 everywhere by construction") to: "revenue = impressions × a deterministic per-creative RPI in [0.03, 0.07] (base `DEMO_RPI` × seeded factor — workstream 07), so each creative's ratio is one stable constant".

- [ ] **Step 4: Add Scenario F4 to `docs/demo-scenarios/fashion.md`**

Append:

```
## Scenario F4: Creative comparison chart (workstream 07)

Covers Phase 7: creative-level RPI comparison and the deterministic
(matplotlib, not AI-drawn) chart tool.

### Scene F4.1 — which creative is winning

**Query:** "Which of the creatives in the Sage Satin Camisole campaign is
winning? Show me a comparison chart."

**Expected tool calls:**
- `compare_creatives_within_campaign(campaign_id=<resolved id>)` and/or
  `generate_creative_comparison_chart(campaign_id=<resolved id>)` — the chart
  tool embeds the comparison payload, so either order (or the chart tool
  alone) is acceptable, but the CHART tool must fire since a chart was asked
  for.

**Pass criteria (check the arithmetic):**
- A chart artifact renders in the UI (PNG; screenshot as evidence) and the
  tool response has `artifact_saved: true`.
- The response names a winner whose RPI is the maximum of the reported
  per-creative RPIs.
- Every reported creative satisfies `revenue ≈ impressions × RPI` (cent
  rounding), RPIs lie in [0.03, 0.07], and are not all identical.
- `chart.chart_data.labels`/`rpi_values` in the tool response match the
  `comparison.creatives` payload exactly (same order, same numbers).
```

- [ ] **Step 5: Provenance amendment in the phase doc**

In `.docs/version2-plan/07-rpi-across-creatives-chart.md`, directly below the existing ws05 amendment blockquote, add:

```
> **Resolved (workstream 07, 2026-07-19):** owner picked Option A at this
> workstream's kickoff gate — a deterministic per-(campaign, video) RPI
> factor in the disposable derivation layer (`app/demo_data/derive.py`,
> `video_rpi()`: `DEMO_RPI ×` seeded factor in [0.6, 1.4] → per-creative RPI
> in [0.03, 0.07], constant across days). RPI-across-creatives is now a real
> comparison; `DEMO_RPI` remains the single base constant. Scenario F3.2's
> criteria updated accordingly.
```

- [ ] **Step 6: Full suite + forbidden-files check**

Run: `git status --porcelain` → only the three files above modified; README.md / DEMO_GUIDE.md absent.
Run: `make test` (venv activated) → all pass. Note: this run exercises the reseeded demo DB path — mock_data regenerates metrics with the new per-creative RPI automatically (delete-and-regen on populate).

- [ ] **Step 7: Commit**

```bash
git add app/agent.py docs/demo-scenarios/fashion.md .docs/version2-plan/07-rpi-across-creatives-chart.md
git commit -m "Wire creative comparison tools into Analytics Agent; update scenarios and phase-doc provenance"
```
