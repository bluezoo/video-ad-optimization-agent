# Live-API Test Tier (Workstream 16) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two honest test tiers — `make test` (unit+e2e, seconds, zero LLM) and `make test-live` (real Vertex: 3-dimension routing evals + live media generation + Gemini judge) — closing Q19 and all 6 carried-in open items.

**Architecture:** Hybrid per the approved working doc: pytest owns inference and isolation (integration conftest with real env, temp-DB copies, per-case control); ADK's own eval stack (`LocalEvalService` + `EvalConfig` criteria) scores each case on three independently-failable dimensions (tools / trajectory / answer); agents-cli supplies the authoring methodology (its `google-agents-cli-eval` skill), a project-free `eval grade`/`compare` reporting layer, and rubric-shape precedent for the media judge (`tests/live/judge.py`, gemini-3.6-flash multimodal).

**Tech Stack:** pytest (+pytest-asyncio `asyncio_mode=auto`), google-adk 2.5.0 evaluation module, google-genai (judge), agents-cli 1.1.0, ruff.

## Global Constraints

- **Owner execution directives are binding** (phase doc §"Execution directives"): every stage lands green and is committed before the next starts; expected answers / judge thresholds / quality bars are NEVER assumed — the controller shows the owner real outputs (answers AND media) via AskUserQuestion and logs answers verbatim in WORK_LOG.md before pinning; "returned 200" is never a pass criterion; WORK_LOG.md updated at every step.
- **Doc sources (directive 4):** every implementer verifies ADK/agents-cli API names against the installed source (`.venv/lib/python3.14/site-packages/google/adk/...`, `/Users/lavi/.local/share/uv/tools/google-agents-cli/...`) and/or the committed research reports (`research/*.md`); if memory disagrees with installed source, source wins. Cite the file you checked in your report.
- **Live tier storage policy (open item 2):** local-first — `GCS_BUCKET` force-unset in the live tier even if `app/.env` sets it; no `storage.googleapis.com` URL may appear in any tool response; media lands under `LOCAL_ASSETS_DIR` (`generated/`, `selected/`, `product-images/`).
- Live-tier judge/agent model: `gemini-3.6-flash` (config default; env-overridable). `GOOGLE_CLOUD_LOCATION=global` for all Gemini 3.x calls.
- No `Co-Authored-By`/AI-attribution trailers in commits or PR bodies. `README.md` untouched. `STATUS.md` only in the main checkout. Never commit `app/.env` (it exists in the worktree, gitignored). Golden prompt tests (`tests/unit/.../golden_*`) stay byte-identical-green — lint/refactor must not alter built prompt text.
- Ruff-clean on all touched files (`make lint` must be green repo-wide after Task 1 and stay green). PostToolUse hook runs `make test-unit` after `app/**/*.py` edits (worktree `.venv` is Python 3.14 — already installed).
- Tests import via `tests.` package (`tests/__init__.py` exists); pytest markers are registered in `pytest.ini:27` — new markers go there.
- Eval/媒体 cost is accepted by the owner ("dont worry about the cost. its important to keep things correct") — but don't loop live calls needlessly; inference results are reused across metric passes.

## Execution protocol for owner gates

Tasks 6–10, 13, and 14 contain **OWNER GATE** steps. Subagents never talk to the owner: the implementer completes the pre-gate steps and reports proposals; the **controller** presents real outputs to the owner (AskUserQuestion, attaching/duplicating media paths), records the verbatim answer in WORK_LOG.md, then dispatches the post-gate steps with the owner's decision as pinned input. A task is not complete until its post-gate steps are green and committed.

---

### Task 1: Repo-wide lint cleanup (stage 0, ws10 carried item 4 — owner approved fold-in)

**Files:**
- Modify: whatever `ruff check app tests` flags (42 errors: I001×11, UP042×7, F541×6, UP045×6, UP006×5, UP035×4, F401×3; 30 auto-fixable)
- Check (read-only): `ruff.toml` (target-version governs the UP042 decision)

**Interfaces:** none (zero behavior change).

- [ ] **Step 1: Baseline.** Run: `.venv/bin/ruff check app tests | tail -5` — expect `Found 42 errors`.
- [ ] **Step 2: Auto-fix.** Run: `.venv/bin/ruff check --fix app tests` (do NOT run `ruff format` — formatting churn is out of scope). Expect ~12 remaining.
- [ ] **Step 3: Manual fixes.** For each remaining error, apply the rule's canonical fix. UP042 (str+Enum → StrEnum): first check `ruff.toml` `target-version` — if `py311`+ convert to `enum.StrEnum` (verify `cfg.APP_MODE == "demo"` str-comparison tests still pass); if lower, add `lint.ignore` for UP042 in `ruff.toml` with a one-line comment instead of converting. UP035/UP006/UP045: modernize typing imports/annotations. F401: delete unused imports. F541: drop needless f-prefix.
- [ ] **Step 4: Verify zero errors.** Run: `make lint` — expect exit 0, no output errors.
- [ ] **Step 5: Full fast suite + golden prompts.** Run: `make test-unit && make test-e2e` — expect 306+ passed / 25 passed (same counts as before, no new failures; golden prompt tests included in unit).
- [ ] **Step 6: Commit.** `git add -A && git commit -m "chore: repo-wide ruff cleanup (ws10 carried item 4) — make lint green"`

### Task 2: Fix the combined-run GCS state leak (stage 1, open item 6)

**Files:**
- Create: `tests/_config_baseline.py`
- Modify: `tests/conftest.py` (import baseline module right after `app.config` import, ~line 46)
- Modify: `tests/unit/test_config.py:10-15` (`_reload_config_after_test`)
- Modify: `tests/unit/test_demo_dataset_gate.py:19-20` (inline cleanup reload)
- Test: `tests/unit/test_config_baseline.py` (new)

**Interfaces:**
- Produces: `tests._config_baseline.restore_config_baseline() -> None` and `tests._config_baseline.BASELINE: dict` — used by Task 4's integration conftest and by any future test that reloads `app.config`.

**Mechanism being fixed (reproduced live at kickoff):** root conftest imports `app.config` at collection (line 45) BEFORE the session env fixture (lines 54-77) pins `GCS_BUCKET=test-bucket` etc. Cleanup `importlib.reload(app.config)` in the two files above re-derives module values under the PINNED env, permanently flipping `app.config.GCS_BUCKET` from its import-time value (None locally) to `"test-bucket"` for the rest of the process — three e2e tests then make real GCS calls (403). Fix: restore an import-time snapshot instead of reloading under polluted env.

- [ ] **Step 1: Reproduce.** Run: `.venv/bin/pytest tests/unit/test_config.py tests/unit/test_demo_dataset_gate.py tests/e2e -q` — expect `1 failed` (test_video_review_table, real 403 to test-bucket).
- [ ] **Step 2: Write the baseline module.**

```python
# tests/_config_baseline.py
"""Import-time snapshot of app.config + restore helper (Phase 16 open item 6).

tests/conftest.py imports app.config at collection time — BEFORE the session
env fixture pins fake values (GCS_BUCKET=test-bucket, ...). Tests that clean
up with importlib.reload(app.config) used to re-derive module values under
the PINNED env, permanently flipping e.g. app.config.GCS_BUCKET from None to
"test-bucket" for the rest of the process. Restoring this snapshot returns
the module to exactly its import-time state, deterministically, regardless
of what the environment looks like at cleanup time.
"""

import app.config as _config_module

BASELINE = {
    name: value
    for name, value in vars(_config_module).items()
    if not name.startswith("__")
}


def restore_config_baseline() -> None:
    """Return app.config to its import-time state (no reload, no env reads)."""
    for name, value in BASELINE.items():
        setattr(_config_module, name, value)
```

- [ ] **Step 3: Import it in root conftest** so the snapshot is captured at pristine collection time — in `tests/conftest.py`, directly after the `from app.config import DB_PATH as _CONFIG_DB_PATH` line:

```python
# Snapshot app.config's import-time state BEFORE any env fixture runs — see
# tests/_config_baseline.py (Phase 16 open item 6).
from tests._config_baseline import restore_config_baseline  # noqa: E402, F401
```

- [ ] **Step 4: Replace the two leaking reloads.** In `tests/unit/test_config.py`, the autouse fixture becomes:

```python
@pytest.fixture(autouse=True)
def _reload_config_after_test(monkeypatch):
    """Each test may reload app.config; restore the import-time baseline afterwards."""
    yield
    monkeypatch.undo()
    restore_config_baseline()
```

with `from tests._config_baseline import restore_config_baseline` added to imports (and `importlib` kept — tests still reload mid-test). In `tests/unit/test_demo_dataset_gate.py`, `TestConfigParsing.test_invalid_value_raises_at_load`'s last two lines become:

```python
        monkeypatch.delenv("DEMO_DATASET")
        restore_config_baseline()  # not reload: reload would re-derive under pinned session env
```

with the same import added.

- [ ] **Step 5: Regression test.**

```python
# tests/unit/test_config_baseline.py
"""Phase 16 open item 6: reload-under-pinned-env must not leak into app.config."""

import importlib

import app.config as config_module
from tests._config_baseline import BASELINE, restore_config_baseline


def test_restore_after_reload_under_pinned_env(monkeypatch):
    monkeypatch.setenv("GCS_BUCKET", "leaky-bucket")
    importlib.reload(config_module)
    assert config_module.GCS_BUCKET == "leaky-bucket"  # the leak, mid-test
    monkeypatch.undo()
    restore_config_baseline()
    assert config_module.GCS_BUCKET == BASELINE["GCS_BUCKET"]


def test_baseline_covers_env_derived_values():
    for key in ("GCS_BUCKET", "GOOGLE_CLOUD_PROJECT", "MODEL", "DB_PATH"):
        assert key in BASELINE
```

(Verify the exact attribute names exist in `app/config.py` before asserting; adjust the tuple to real names.)

- [ ] **Step 6: Verify.** Run: `.venv/bin/pytest tests/unit/test_config.py tests/unit/test_demo_dataset_gate.py tests/unit/test_config_baseline.py tests/e2e -q` — expect all pass. Then the full combined run: `.venv/bin/pytest tests/unit tests/e2e -q` — all pass.
- [ ] **Step 7: Commit.** `git commit -m "fix(tests): restore app.config import-time baseline instead of reloading under pinned env (Phase 16 item 6)"`

### Task 3: Tier split — make targets + markers (stage 2)

**Files:**
- Modify: `Makefile` (lines 172-210 region: `test`, new `test-live`; help text)
- Modify: `pytest.ini:27-31` (add `live` marker)
- Create: `tests/live/__init__.py` (empty package so the pytest path exists)

**Interfaces:**
- Produces: `make test` = unit+e2e only; `make test-live` = `pytest tests/integration tests/live`; `live` pytest marker. Tasks 11-14 put tests in `tests/live/`.

- [ ] **Step 1: Makefile.** Replace the `test:` target and add `test-live` after `test-e2e`:

```make
## Run fast tests (unit + e2e — seconds, zero LLM calls; the everyday loop)
test: test-unit test-e2e
	@echo ""
	@echo "All fast tests passed!"

## Run LIVE tier: routing evals + live media + judge (real Vertex APIs, costs money)
test-live:
	@echo "Running LIVE tier (real Vertex APIs — requires app/.env)..."
	@test -f app/.env || { echo "ERROR: app/.env missing — the live tier needs real credentials (see SETUP_INSTRUCTIONS.md)"; exit 1; }
	@if [ -d ".venv" ]; then \
		.venv/bin/pytest tests/integration tests/live -v --tb=short; \
	else \
		pytest tests/integration tests/live -v --tb=short; \
	fi
```

Keep `test-integration` (targeted runs) and `test-all`/`test-coverage` as-is (`pytest tests/` already includes `tests/live`). Update the `## ...` help comments so `make help` describes the tier split.

- [ ] **Step 2: pytest.ini marker.** Add under `markers =`: `    live: live-tier tests hitting real Vertex APIs (media generation + judge)`
- [ ] **Step 3: Create `tests/live/__init__.py`** (empty).
- [ ] **Step 4: Verify.** `make test` → unit+e2e only, green, no integration output. `make test-live` with `app/.env` present → runs tests/integration (current state: passes vacuously — Task 4 fixes that) without erroring on the empty tests/live dir.
- [ ] **Step 5: Commit.** `git commit -m "feat(make): split fast tier (test=unit+e2e) from live tier (test-live) + live marker"`

### Task 4: Integration conftest — real env, local-first pin, DB isolation (stage 3a)

**Files:**
- Create: `tests/integration/conftest.py`
- Test: `tests/integration/test_live_env_smoke.py` (new)

**Interfaces:**
- Consumes: `tests._config_baseline.restore_config_baseline` (Task 2), `tests.conftest._copy_main_db_to_temp`.
- Produces: autouse fixtures `live_real_environment` and `isolated_live_db` for everything under `tests/integration/`; Task 12+ replicates the pattern for `tests/live/` (a one-line `from tests.integration.conftest import *` is NOT acceptable — Task 12 creates `tests/live/conftest.py` importing the two fixture functions explicitly).

- [ ] **Step 1: Write the conftest.**

```python
# tests/integration/conftest.py
"""Live-tier environment for tests/integration (Q19 repair, stage 3a).

The root conftest pins FAKE env at session start (unit/e2e isolation) and
imports app.config at collection time. The live tier needs the REAL
environment from app/.env — re-applied per test, with app.config reloaded so
module-level values match, and the import-time baseline restored afterwards
so fast-tier tests in the same process never see live config.

Storage policy (Phase 16 open item 2): live tier is LOCAL-FIRST —
GCS_BUCKET is force-unset even when the developer's app/.env sets it.
"""

import importlib
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

import app.config as config_module
from tests._config_baseline import restore_config_baseline
from tests.conftest import _copy_main_db_to_temp

ENV_FILE = Path(__file__).resolve().parents[2] / "app" / ".env"


@pytest.fixture(autouse=True)
def live_real_environment(monkeypatch):
    """Real Vertex env from app/.env for the duration of one test."""
    if not ENV_FILE.exists():
        pytest.skip("app/.env missing — live tier requires real credentials")
    real = {k: v for k, v in dotenv_values(ENV_FILE).items() if v}
    project = real.get("GOOGLE_CLOUD_PROJECT")
    if not project or project == "test-project":
        pytest.fail("app/.env must set a real GOOGLE_CLOUD_PROJECT for the live tier")
    for key, value in real.items():
        monkeypatch.setenv(key, value)
    # Gemini 3.x models need the global endpoint (CLAUDE.md gotcha).
    monkeypatch.setenv(
        "GOOGLE_CLOUD_LOCATION", real.get("GOOGLE_CLOUD_LOCATION", "global")
    )
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    # Local-first storage: never GCS in the live tier (open item 2).
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    importlib.reload(config_module)
    assert config_module.GCS_BUCKET is None
    yield
    monkeypatch.undo()
    restore_config_baseline()


@pytest.fixture(autouse=True)
def isolated_live_db(live_real_environment, monkeypatch):
    """Live agent runs execute REAL tools that mutate the DB — use a copy."""
    db_path = _copy_main_db_to_temp()
    monkeypatch.setattr(config_module, "DB_PATH", db_path)
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass
```

(Implementer: verify the exact `app/config.py` attribute name for the project id — adjust the assert in Step 2's smoke test to the real name; verify `dotenv_values` import — python-dotenv is already pinned in app/requirements.txt.)

- [ ] **Step 2: Smoke test.**

```python
# tests/integration/test_live_env_smoke.py
"""Proves the live tier genuinely sees the real environment (Q19 guardrail)."""

import pytest

import app.config as config_module

pytestmark = pytest.mark.integration


def test_live_env_reaches_config():
    assert config_module.GOOGLE_CLOUD_PROJECT not in (None, "", "test-project")
    assert config_module.GCS_BUCKET is None  # local-first pin (open item 2)


def test_db_is_an_isolated_copy(isolated_live_db):
    assert str(config_module.DB_PATH) == str(isolated_live_db)
    assert "test_campaigns_" in str(isolated_live_db)
```

- [ ] **Step 3: Verify both tiers.** `.venv/bin/pytest tests/integration/test_live_env_smoke.py -q` → 2 passed. Then `make test` → still green (fast tier untouched); `.venv/bin/pytest tests/unit tests/e2e tests/integration/test_live_env_smoke.py -q` → green (combined-process safety, builds on Task 2).
- [ ] **Step 4: Commit.** `git commit -m "feat(tests): integration conftest — real env from app/.env, local-first pin, DB isolation (Q19 stage 3a)"`

### Task 5: Eval harness with vacuity guard + 3-dimension scoring (stage 3b)

**Files:**
- Create: `tests/integration/eval_harness.py`
- Create: `tests/integration/eval_sets/live_eval_config.json`
- Modify: `tests/integration/test_agents.py` (rewire to harness; xfail-as-authored markers)
- Test: `tests/integration/test_eval_harness_guard.py` (new)

**Interfaces:**
- Consumes: Task 4's fixtures (autouse — nothing to wire).
- Produces:
  - `run_eval_set(eval_set_path: str, *, record_to: str | None = None) -> list[CaseOutcome]` (async) — runs inference ONCE per case via ADK's eval stack, then scores the three dimensions from `live_eval_config.json` against the same inference results.
  - `CaseOutcome` dataclass: `eval_id: str`, `inference_ok: bool`, `error_message: str | None`, `actual_tool_calls: list[dict]` (ordered, incl. `transfer_to_agent` entries), `final_response_text: str`, `dimensions: dict[str, DimensionOutcome]` where `DimensionOutcome` has `score: float | None`, `threshold: float`, `passed: bool`.
  - `assert_eval_outcomes(outcomes: list[CaseOutcome], *, expect_cases: int) -> None` — the vacuity guard + per-dimension gate.
  - CLI recorder: `python -m tests.integration.record_actuals <eval_set.json> <out.json>` dumping actual trajectories + answers (used by Tasks 6-10 calibration and Task 15 trace export).

- [ ] **Step 1: Verify the installed API surface (directive 4).** Read `.venv/lib/python3.14/site-packages/google/adk/evaluation/local_eval_service.py`, `agent_evaluator.py`, `eval_config.py` (or equivalents found via `grep -r "class EvalConfig" .venv/.../adk/evaluation/`). Confirm against `research/adk-eval-docs-context7.md`: how to (a) load an eval set file, (b) run inference (`LocalEvalService.perform_inference` / equivalent) getting per-case inference status, (c) run metric evaluation over existing inference results with an `EvalConfig`, (d) which of `final_response_match_v2` / `rubric_based_final_response_quality_v1` exist in **installed 2.5.0**. Record findings at the top of `eval_harness.py` as a comment citing file paths.
- [ ] **Step 2: Write `live_eval_config.json`** — three named dimensions, each a NATIVE ADK criteria payload (keep formats native, orchestration ours — directive 3):

```json
{
  "dimensions": {
    "tools": {
      "criteria": {
        "tool_trajectory_avg_score": {"threshold": 1.0, "match_type": "ANY_ORDER"}
      }
    },
    "trajectory": {
      "criteria": {
        "tool_trajectory_avg_score": {"threshold": 1.0, "match_type": "IN_ORDER"}
      }
    },
    "answer": {
      "criteria": {
        "final_response_match_v2": {
          "threshold": 0.75,
          "judge_model_options": {"judge_model": "gemini-3.6-flash", "num_samples": 3}
        }
      }
    }
  }
}
```

If Step 1 finds `final_response_match_v2` absent/differently-shaped in 2.5.0, substitute the closest installed judge criterion and note it in the WORK_LOG; thresholds here are STARTING values — calibrated per set in Tasks 6-10 with owner sign-off.

- [ ] **Step 3: Implement the harness.** Structure (exact ADK calls per Step 1's findings — inference runs ONCE, metric passes reuse results):

```python
# tests/integration/eval_harness.py  (skeleton — complete with Step-1-verified API)
"""Live eval harness: single-inference, 3-dimension scoring, vacuity guard.

Why not AgentEvaluator.evaluate(): its pytest aggregation only compares mean
metric scores and never inspects per-case final_eval_status — when every
inference fails there are no scores and the assert passes VACUOUSLY (Q19,
confirmed from source; see research/adk-eval-docs-context7.md). This harness
drives the same underlying eval stack but asserts inference status per case.
"""
from dataclasses import dataclass, field


@dataclass
class DimensionOutcome:
    score: float | None
    threshold: float
    passed: bool


@dataclass
class CaseOutcome:
    eval_id: str
    inference_ok: bool
    error_message: str | None
    actual_tool_calls: list[dict]
    final_response_text: str
    dimensions: dict[str, DimensionOutcome] = field(default_factory=dict)


_INFRA_MARKERS = (
    "credential", "permission denied", "permission_denied", "403", "quota",
    "resource_exhausted", "429", "unavailable", "503", "deadline",
    "connection", "getaddrinfo",
)  # kept from the old test_agents.py — infra breakage may xfail, never PASS


async def run_eval_set(eval_set_path, *, record_to=None):
    ...  # load set -> perform inference once per case -> per-dimension metric
         # evaluation over the SAME inference results -> CaseOutcome list;
         # if record_to: json.dump actual trajectories/answers (calibration +
         # agents-cli trace export, Task 15)


def assert_eval_outcomes(outcomes, *, expect_cases):
    import pytest
    if len(outcomes) != expect_cases:
        pytest.fail(f"expected {expect_cases} eval cases, only {len(outcomes)} produced results — partial/zero runs must not pass")
    failed_inference = [o for o in outcomes if not o.inference_ok]
    if failed_inference:
        msgs = "; ".join(f"{o.eval_id}: {o.error_message}" for o in failed_inference)
        if all(any(m in (o.error_message or "").lower() for m in _INFRA_MARKERS) for o in failed_inference):
            pytest.xfail(f"integration infrastructure unavailable: {msgs}")
        pytest.fail(f"inference failed (NOT infra): {msgs}")
    dim_failures = [
        f"{o.eval_id}[{name}]: score={d.score} < {d.threshold}"
        for o in outcomes for name, d in o.dimensions.items() if not d.passed
    ]
    if dim_failures:
        pytest.fail("eval dimension failures:\n  " + "\n  ".join(dim_failures))
```

- [ ] **Step 4: Rewire `tests/integration/test_agents.py`.** Each test class calls `outcomes = await run_eval_set(get_eval_set_path("<set>.test.json")); assert_eval_outcomes(outcomes, expect_cases=<N>)`. Remove the old `_xfail_if_infrastructure` wrapper (harness owns it). Mark each of the five tests `@pytest.mark.xfail(reason="eval set authored pre-transfer_to_agent (ws09 discovery) — repaired in Phase 16 stage 4", strict=False)` — they now genuinely run and genuinely fail; each repair task removes its marker.
- [ ] **Step 5: Vacuity-guard break test.**

```python
# tests/integration/test_eval_harness_guard.py
"""Deliberate-break checks: zero/partial inference must never PASS (Q19)."""

import pytest
from _pytest.outcomes import Failed, XFailed

from tests.integration.eval_harness import (
    CaseOutcome, assert_eval_outcomes,
)

pytestmark = pytest.mark.integration


def _case(eval_id="c1", ok=True, err=None):
    return CaseOutcome(eval_id=eval_id, inference_ok=ok, error_message=err,
                       actual_tool_calls=[], final_response_text="")


def test_all_inference_failed_never_passes():
    bad = [_case(ok=False, err="something exploded (not infra-shaped)")]
    with pytest.raises(Failed):
        assert_eval_outcomes(bad, expect_cases=1)


def test_infra_failure_xfails_not_passes():
    bad = [_case(ok=False, err="403 PERMISSION_DENIED on aiplatform")]
    with pytest.raises(XFailed):
        assert_eval_outcomes(bad, expect_cases=1)


def test_partial_results_never_pass():
    with pytest.raises(Failed):
        assert_eval_outcomes([_case()], expect_cases=4)
```

- [ ] **Step 6: Recorder CLI** (`tests/integration/record_actuals.py` with `if __name__ == "__main__":` + `python -m` entry): args `<eval_set.json> <out.json>`, runs `run_eval_set(..., record_to=out)` under the same env bootstrap as the conftest (factor the env-apply into a plain function the conftest fixture and the CLI share).
- [ ] **Step 7: Verify.** `.venv/bin/pytest tests/integration -q` → smoke tests + guard tests pass, five eval tests xfail (genuinely running — watch runtime: minutes, not the old vacuous ~5s; capture the timing in the report as evidence). `make test` still green/fast.
- [ ] **Step 8: Commit.** `git commit -m "feat(tests): live eval harness — single-inference 3-dimension scoring + vacuity guard (Q19 stage 3b)"`

### Tasks 6–10: Repair the five eval sets, one per task/commit (stage 4)

Task 6: `coordinator.test.json` · Task 7: `campaign_agent.test.json` · Task 8: `media_agent.test.json` · Task 9: `analytics_agent.test.json` · Task 10: `review_agent.test.json`.

**Files (per task):**
- Modify: `tests/integration/eval_sets/<set>.test.json`
- Modify: `tests/integration/test_agents.py` (remove that set's xfail marker; set `expect_cases`)
- Create: `.docs/version2-plan/working-docs/16-live-api-testing/calibration/<set>-actual.json` (recorded actuals, committed as evidence)
- Possibly modify: `tests/integration/eval_sets/live_eval_config.json` (threshold calibration — note every change in WORK_LOG)

**Interfaces:** consumes Task 5's harness + recorder verbatim.

**Procedure (identical steps each task; each task's brief carries this list in full):**

- [ ] **Step 1: Record actuals.** `.venv/bin/python -m tests.integration.record_actuals tests/integration/eval_sets/<set>.test.json .docs/version2-plan/working-docs/16-live-api-testing/calibration/<set>-actual.json` — captures the live trajectory (with `transfer_to_agent` wrapping) and the live final answer per case.
- [ ] **Step 2: Draft repairs.** For each case, rewrite `intermediate_data.tool_uses` to the REAL shape — coordinator routing appears as an ordinary entry first, e.g. for `campaign_agent.test.json`'s `list-all-campaigns` case:

```json
"tool_uses": [
  {"name": "transfer_to_agent", "args": {"agent_name": "campaign_agent"}},
  {"name": "list_campaigns", "args": {}}
]
```

Keep `args` minimal-but-meaningful (ids and required params only — the live model may phrase optional args differently; anything volatile is a calibration decision, not a guess). Draft a proposed `final_response` reference per case FROM the recorded live answer.

- [ ] **Step 3: OWNER GATE (controller).** Present per case: the query, the recorded live answer verbatim, the proposed reference/expected-content, and any trajectory ambiguity (e.g. does create-campaign legitimately call `list_products` first?). Owner's answers are logged verbatim in WORK_LOG.md before anything is pinned (directive 6).
- [ ] **Step 4: Pin + green.** Write the repaired set with owner-approved references; remove that set's xfail marker; run `.venv/bin/pytest tests/integration/test_agents.py -k <set-test> -q` → PASS on all three dimensions. If a dimension needs a threshold change, change `live_eval_config.json` ONLY with the owner's Step-3 answer covering it (never silently — the agents-cli skill's rule: fix the agent, not the thresholds, unless the owner says the expectation itself was wrong).
- [ ] **Step 5: Deliberate-break check (Task 6 only, the ws09 validation checkbox).** Corrupt one expected tool name (`list_campaigns` → `list_campaignsX`), rerun → must FAIL on the tools dimension; revert → PASS. Record in WORK_LOG.
- [ ] **Step 6: Commit.** `git commit -m "feat(evals): repair <set> to live transfer_to_agent trajectories + owner-approved answers (stage 4)"`

Notes: `coordinator.test.json` (Task 6) goes first — it teaches the real routing shape; its findings inform the other four briefs. `create-campaign-beverage` (campaign set) mutates the DB — Task 4's `isolated_live_db` already isolates it; its `args` pin (`product_id: 23`) must be re-verified against seeded data during calibration.

### Task 11: New eval cases — the two ws14 candidates (stage 4b)

**Files:**
- Modify: `tests/integration/eval_sets/campaign_agent.test.json` (add case) or create `tests/integration/eval_sets/regressions.test.json` — implementer picks based on Task 7's final structure; a new set needs a matching test function + `expect_cases`.
- Modify: `tests/unit/test_video_tools.py` or nearest fit (legacy-fields assertion is a FAST-tier unit test, not live)

**Interfaces:** consumes Task 5 harness; ws14 WORK_LOG:147-151 is the source of truth for both cases.

- [ ] **Step 1: Cold-start duplicate-product eval case (live).** Query: `Create a campaign for the Urban Puffer Jacket at Macy's Herald Square in New York` with NO prior listing turn. Expected trajectory: resolve the SEEDED product (via `list_products`/`get_product` or direct id) → `create_campaign`; expected to NOT contain `create_product`. Record actuals first (this may genuinely still fail — ws14 observed the duplicate-create). **OWNER GATE:** show the live trajectory; if the agent still duplicates, ask whether to (a) pin the correct expectation and fix the agent instruction in THIS workstream, or (b) pin as xfail-documented regression for a follow-up. Log the answer; implement accordingly.
- [ ] **Step 2: Legacy variation fields (fast tier).** Unit test asserting saved variation JSON contains no `model_ethnicity`/`activity` keys — locate the writer (grep `variation_params` in `app/tools/video_tools.py`) and assert on its output shape for a generated variation. If the writer still emits them, same OWNER GATE pattern: fix now vs documented xfail.
- [ ] **Step 3: Verify + commit.** Both tiers green (or owner-sanctioned xfails). `git commit -m "test: ws14 candidate eval cases — cold-start product resolution + legacy variation fields"`

### Task 12: Live media-generation tests (stage 5, phase-doc step 4 + open item 2)

**Files:**
- Create: `tests/live/conftest.py` (imports Task 4's two fixture functions explicitly and re-registers them autouse for tests/live)
- Create: `tests/live/test_media_pipeline.py`
- Test markers: `live` + `slow` + `veo`

**Interfaces:**
- Consumes: `app.tools.video_tools.generate_video_ad` / the two-stage pipeline entry points (verify exact signatures in `app/tools/video_tools.py` — Stage-1 image at ~:249, Veo helpers `_wait_for_veo_operation`/`_extract_video_bytes` from ws14), archetypes from `app/tools/prompt_archetypes.py:16-24`.
- Produces: generated media file paths consumed by Task 13's judge tests (module-scoped fixture caching the generated paths so judge tests reuse instead of regenerate).

- [ ] **Step 1: `tests/live/conftest.py`** — re-export Task 4's fixtures (import the functions and wrap with `pytest.fixture(autouse=True)` locally), plus a session-scoped `generated_media` registry dict fixture.
- [ ] **Step 2: Wearable + non-wearable pipeline tests.** One test per archetype path, calling the real tool function (not the agent — routing is Tasks 6-10's job):
  - wearable: a seeded fashion product (calibrate id from seeded data) → expect fashion-style filename, `reference_image_used` honest per whether a reference exists locally;
  - non-wearable: a retail-core product (e.g. the cold brew) → product-centric filename, `product_only` archetype.
  Assertions (the tool CONTRACT, not 200s): `status == "success"`; video file exists under `LOCAL_ASSETS_DIR/generated/` and is >100KB; DB row updated to the success status; `reference_image_used` field matches reality; NO `storage.googleapis.com` substring anywhere in `json.dumps(result)` (reuse the assertion shape from `tests/unit/test_url_policy.py`); record actual image resolution + video duration/fps into the test log AND `calibration/media-metadata.json` (Q14/Q15 evidence, open item 5).
- [ ] **Step 3: Register outputs** in the `generated_media` fixture for Task 13.
- [ ] **Step 4: Verify.** `.venv/bin/pytest tests/live -m "live" -q` (budget ~5-15 min; Veo polling helper caps at 600s/job). Fast tier untouched.
- [ ] **Step 5: Commit.** `git commit -m "feat(tests): live media pipeline tests — wearable + non-wearable, local-first URL policy (stage 5)"`

### Task 13: From-scratch onboarding live case (stage 5b, open item 3)

**Files:**
- Create: `tests/live/test_onboarding_from_scratch.py`

**Interfaces:** consumes `app/tools/onboarding_tools.py` (`create_product`, `generate_product_image` ~:215), `empty_test_db` fixture pattern (root conftest:180-198), Task 12's conftest.

- [ ] **Step 1: Test:** on an EMPTY DB (replicate `empty_test_db` inline against the live conftest's monkeypatched `DB_PATH`): `create_product` (a non-fashion product, e.g. artisan coffee beans) → `generate_product_image` against the REAL image model → attach to a campaign. Assert: product row exists; image file lands under `product-images/`; `image_status: available`; campaign attach succeeds; no GCS URLs. Register the image in `generated_media` for judge review (open item 3 says judge it like any other output).
- [ ] **Step 2: Verify + commit.** `git commit -m "feat(tests): from-scratch onboarding live case (open item 3)"`

### Task 14: Gemini judge — rubric review of generated media (stage 6, phase-doc step 5)

**Files:**
- Create: `tests/live/judge.py`
- Create: `tests/live/test_media_judge.py`
- Modify: `tests/live/test_media_pipeline.py` / `test_onboarding_from_scratch.py` only if fixture plumbing needs it

**Interfaces:**
- Consumes: `generated_media` registry (Tasks 12-13); rubric sources `app/tools/prompt_archetypes.py:16-24` + `app/tools/prompt_builders.py:32-40` (`_NO_TEXT_BLOCK`/`_AUDIO_BLOCK`); `google.genai` client with `config.MODEL` (gemini-3.6-flash) on Vertex `global`.
- Produces: `judge_image(path, *, archetype: str, request_context: str) -> JudgeVerdict` and `judge_video(path, *, archetype, request_context) -> JudgeVerdict`; `JudgeVerdict` = dict of named checks, each `{"verdict": "pass"|"fail", "severity": "hard"|"warn", "evidence": str}`.

- [ ] **Step 1: Implement `judge.py`.** genai client (Vertex, global), send image bytes / video bytes (video: pass the mp4 directly — gemini-3.6-flash accepts video input on Vertex; if a size/format limit bites, fall back to sampling 4 evenly-spaced frames via the thumbnail-extraction approach already used in `app/tools/video_tools.py` — check for an existing frame/thumbnail helper before writing one). Structured output: `response_schema` JSON with per-check verdicts + one-line evidence. Checks (initial severity per phase-doc open question 1 default):
  - `subject_matches_archetype` (**hard**): wearable → human model wearing the garment; `product_only`/product-hero → NO humans, product is the hero;
  - `no_rendered_text` (**hard**): no captions/titles/badges/overlays/watermarks beyond the product's own packaging;
  - `setting_mood_plausible` (**warn**): setting/mood plausibly match the request context;
  - videos additionally `no_captions_any_frame` (**hard**) — rubric text states audio is NOT verified (prompt-policy + frames only; no over-claiming).
- [ ] **Step 2: `test_media_judge.py`:** for every entry in `generated_media`, run the matching judge; test FAILS on any hard-check fail, WARNS (via `warnings.warn` + report line) on warn-checks. Chart variant: generate one RPI chart via the real chart tool (ws07 coverage) and judge with an inverted text rule (axes/labels REQUIRED and legible, correct creative count per the deterministic seeded data).
- [ ] **Step 3: Calibration run + OWNER GATE (controller).** Run judge over all Task-12/13 media; present to the owner: each media file path (so they can open it), the judge's per-check verdicts, and the proposed hard/warn split. Ask: do these verdicts match your eye? which checks should block vs warn? Pin ONLY after the answers land in WORK_LOG (directive 6; phase-doc open question 1 is decided here, and `99-open-questions.md` gets amended with the outcome in Task 16).
- [ ] **Step 4: Verify.** Full `make test-live` — evals + media + judge all green in one run. Capture total wall time + rough cost notes for Task 16's docs.
- [ ] **Step 5: Commit.** `git commit -m "feat(tests): gemini-3.6-flash media judge with archetype/no-text rubric (stage 6)"`

### Task 15: agents-cli grading layer (stage 7, directive 3)

**Files:**
- Create: `scripts/eval_grade_report.py` (converts harness `record_to` output → vertexai EvaluationDataset trace JSON; invokes `agents-cli eval grade`)
- Create: `Makefile` target `test-live-report`
- Output dir: `artifacts/grade_results/` (add to `.gitignore`)

**Interfaces:** consumes Task 5's recorder output format; `agents-cli eval grade --traces <file> --output <dir> --config <metrics.yaml>` (project-free mode — exact flags/format per `research/agents-cli-architecture.md` §grade, re-verify against `agents-cli eval grade --help`).

- [ ] **Step 1: Trace conversion + grade config.** Map each recorded case → an EvaluationDataset row ({prompt, response, agent_data with tool calls}); write a minimal metrics config using built-ins that mirror our dimensions (`tool_use_quality`, `final_response_quality` — exact names from `agents-cli eval metric list` or the skill's reference).
- [ ] **Step 2: Run + evaluate fit.** `make test-live-report` produces `results_<ts>.json` + HTML. Compare its verdicts with our harness's on the same run. Write the fit verdict (keep as reporting layer / promote / drop — with evidence) into WORK_LOG and `research/agents-cli-architecture.md` addendum. This target is INFORMATIONAL (not a gate) unless the owner upgrades it.
- [ ] **Step 3: Commit.** `git commit -m "feat(eval): agents-cli grade/compare reporting layer over live eval traces (stage 7)"`

### Task 16: Docs, targets, and open-question cleanup (stage 8, open items 4+5)

**Files:**
- Modify: `CLAUDE.md` (Commands section: new tier map incl. `test-live`; REWRITE the "integration eval suite passes vacuously" gotcha — it's now wrong; new text records the refined mechanism (AgentEvaluator aggregation gap, fixed by the harness) and the live-tier cost note "owner: cost accepted, correctness first")
- Modify: `Makefile` `reset-db` echo (line ~263: "22 fashion products" → "28 products (22 fashion + 6 retail core), DEMO_DATASET-dependent")
- Modify: `SETUP_INSTRUCTIONS.md` (live tier setup: app/.env requirements, `make test-live`, expected runtime/cost profile)
- Modify: `DEMO_GUIDE.md` § "Workstream Testing Journeys" (new `### Workstream 16` journeys: run `make test` fast, run `make test-live`, deliberate-break demo, judge-report reading; prune nothing — no prior journeys invalidated unless Tasks 6-14 changed agent-visible behavior, re-check then)
- Modify: `.docs/version2-plan/16-live-api-testing.md` (mark steps/items done with provenance notes), `.docs/version2-plan/99-open-questions.md` (Q19 → resolved-by-ws16 wording; Q14/Q15 amended with the recorded resolution/duration evidence from `calibration/media-metadata.json`; phase-doc open questions 1-2 → answered per owner's Task-14 gate decisions)
- WORK_LOG: Q14/Q15 evidence block (open item 5)

**Interfaces:** consumes outcomes of all prior tasks; nothing downstream.

- [ ] Step 1: Apply every edit above (each doc claim must match what actually shipped — re-read the final Makefile/conftest before writing prose).
- [ ] Step 2: `make lint && make test` green; `git commit -m "docs: Phase 16 tier map, gotcha rewrite, journeys, Q14/Q15/Q19 amendments (stage 8)"`

### Task 17: Demo-asset bundle publish + live verify (stage 9, open item 1 — owner-assisted)

**Files:** none in-repo expected (env var + verification evidence); WORK_LOG entry.

- [ ] **Step 1: Build.** `make demo-assets-build SRC=<the ws15 asset folder — ask owner for the path if not in product-images/>` → zip + sha256 printed.
- [ ] **Step 2: OWNER GATE (controller):** owner uploads the zip to Drive (anyone-with-link) and provides the file id; set `DEMO_ASSETS_DRIVE_ID` in `app/.env` (NOT committed).
- [ ] **Step 3: Live verify.** Wipe `product-images/` marker state per `scripts/demo_assets.py` mechanics (MARKER_NAME line 42), run `make demo-assets` → download, sha256-verify, install; run again → marker no-op. Seeded products report `image_status: available` (check via a quick sqlite/tool query). Evidence + timings → WORK_LOG.
- [ ] **Step 4:** If any code fix is needed (download path bug etc.), fix + test + commit; else WORK_LOG entry only.

### Task 18: Workstream verification (verify phase)

Per `verifying-with-demo-scenarios` (STATUS → `verify in progress` first):

- [ ] **Step 1: Full live tier as primary evidence.** Fresh `make test-live` end-to-end; attach the full output + timing to WORK_LOG (checkpoint 5). Both deliberate-break validation boxes from the phase doc re-confirmed on the final code.
- [ ] **Step 2: F1 regression via demo-scenario-verifier** (`docs/demo-scenarios/fashion.md` F1, port 8501, sequential) — test-infra work must not have changed agent behavior; PASS required.
- [ ] **Step 3:** WORK_LOG checkpoint 5, then `requesting-code-review` (whole branch) → `finishing-a-development-branch` (PR into version_2, self-merge on owner confirmation).

---

## Self-review notes

- Spec coverage: phase-doc steps 1 (Task 4-5), 2 (Tasks 6-10), 3 (no-op — re-verified implicitly by every live run on the default model; recorded in Task 16's phase-doc amendment), 4 (Task 12), 5 (Task 14), 6 (Tasks 3+16). Open items: 1→Task 17, 2→Tasks 4+12, 3→Task 13, 4→Task 16, 5→Tasks 12+16, 6→Task 2. Directives: 1→coverage matrix realized across Tasks 6-14 (ws01-ws15 rows in the working doc; Task 16 re-checks the matrix against shipped tests), 2→Task 5's dimension design, 3→agents-cli skill methodology in Tasks 6-10 + Task 15, 4→Global Constraints + Task 5 Step 1, 5→18 small tasks/commits, 6→OWNER GATE steps, 7→WORK_LOG steps throughout. ws10 lint item→Task 1; ws14 candidates→Task 11.
- Known intentional deviation from the phase doc: the vacuity guard asserts per-case inference status via the harness instead of capturing the `local_eval_service` logger — research showed the logger-capture premise was wrong (LocalEvalService doesn't swallow; AgentEvaluator's aggregation does). Phase doc gets a provenance amendment in Task 16.
- Placeholders check: Tasks 5-10 and 14 contain calibration-dependent content by DESIGN (directive 6 forbids pre-pinning expected answers/thresholds); each such value has an explicit recording step, owner gate, and WORK_LOG landing spot instead of a guessed constant.
