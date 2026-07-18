# APP_MODE Config Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed, validated `APP_MODE=demo|connected` config value (default `demo`, invalid values fail startup) with zero behavior change, forwarded by both explicit deploy paths and documented.

**Architecture:** A `str`-Enum `AppMode` plus a validated module-level `APP_MODE` constant in `app/config.py`, matching the file's flat-constants house style. Nothing consumes the value in this phase — Phase 11a later resolves it internally to a provider selection. Deploy wiring adds one env-var forward to each of `scripts/deploy.sh` and `scripts/deploy_ae_inline.py`.

**Tech Stack:** Python stdlib only (`enum`, `os`); pytest with the existing `importlib.reload` pattern in `tests/unit/test_config.py`.

## Global Constraints

- **Zero behavior change:** do NOT touch `populate_mock_data()`, `app/agent.py` (line 111's import-time init stays), anything in `app/tools/`, any agent instruction, `README.md`, or `DEMO_GUIDE.md`.
- **No consumer of `APP_MODE`:** no guard, no factory, no `require_connected_adapters()` — explicitly out of scope per the phase doc's corrected scope.
- Semantics, exact: unset → `demo`; empty/whitespace value → `demo` (treated as unset); `demo` → `demo`; `connected` → `connected` (valid, inert); anything else → **`ValueError` raised at config-load time** (never `ImportError`-shaped — `scripts/deploy_ae_inline.py:259` catches `ImportError` and would mislabel it; never a silent downgrade to demo).
- Input normalization: `.strip().lower()` before matching (so `APP_MODE=Connected ` works; `APP_MODE=garbage` still fails).
- Enum style: `class AppMode(str, Enum)` (house style per `app/models/video_properties.py:17-87`; `Literal` is used nowhere in `app/`).
- Deploy wiring covers BOTH explicit paths (owner decision 2026-07-18): `scripts/deploy.sh` (`--set-env-vars`) AND `scripts/deploy_ae_inline.py` (`env_vars` dict ~line 304). `scripts/deploy_ae.sh` untouched (reads `app/.env` automatically). The `app/agent_engine_app.py` force-set workaround is deferred to Phase 11/12 — do not add it.
- No AI-attribution trailers in commit messages.
- The PostToolUse hook runs `make test-unit` after every `app/**/*.py` edit, and `tests/conftest.py:45` imports `app.config` at collection time — write `config.py` changes as one complete edit (enum + validation + constant together), never a partial state.

---

### Task 1: `AppMode` enum + validated `APP_MODE` in config, with tests

**Files:**
- Modify: `app/config.py` (new section after `import os`, before the "Model configuration" section)
- Test: `tests/unit/test_config.py` (append a new test class; reuse the existing autouse reload fixture at lines 10-16 — do not add a new fixture)

**Interfaces:**
- Produces: `app.config.AppMode` (`str`-Enum with members `DEMO = "demo"`, `CONNECTED = "connected"`) and `app.config.APP_MODE` (an `AppMode` instance). Task 2 and 3 reference the env var name `APP_MODE` and default string `"demo"` only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
class TestAppMode:
    """Phase 6: typed APP_MODE config value (demo|connected), no consumers yet."""

    def test_unset_defaults_to_demo(self, monkeypatch):
        monkeypatch.delenv("APP_MODE", raising=False)
        cfg = importlib.reload(config_module)
        assert cfg.APP_MODE is cfg.AppMode.DEMO

    def test_explicit_demo_is_demo(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "demo")
        cfg = importlib.reload(config_module)
        assert cfg.APP_MODE is cfg.AppMode.DEMO

    def test_connected_is_valid_and_readable(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "connected")
        cfg = importlib.reload(config_module)
        assert cfg.APP_MODE is cfg.AppMode.CONNECTED

    def test_value_is_normalized(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "  Connected ")
        cfg = importlib.reload(config_module)
        assert cfg.APP_MODE is cfg.AppMode.CONNECTED

    def test_empty_value_means_unset(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "")
        cfg = importlib.reload(config_module)
        assert cfg.APP_MODE is cfg.AppMode.DEMO

    def test_invalid_value_raises_valueerror_at_load(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "garbage")
        with pytest.raises(ValueError, match="APP_MODE"):
            importlib.reload(config_module)

    def test_app_mode_is_str_enum(self, monkeypatch):
        monkeypatch.delenv("APP_MODE", raising=False)
        cfg = importlib.reload(config_module)
        assert isinstance(cfg.APP_MODE, cfg.AppMode)
        assert cfg.APP_MODE == "demo"  # str-enum: comparable to its string value
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py::TestAppMode -v`
Expected: 7 failures/errors, each `AttributeError: ... has no attribute 'AppMode'` (or `'APP_MODE'`).

- [ ] **Step 3: Implement in `app/config.py`**

Add `from enum import Enum` below `import os` (line 17), then insert this section between `import os` and the `# Model configuration` block:

```python
from enum import Enum

# App mode (Phase 6): demo|connected, default demo. Nothing consumes this yet —
# Phase 11a resolves it internally to a data-provider selection (demo → the
# synthetic provider, connected → the live one). APP_MODE stays the ONLY
# user-facing mode knob; do not add a second mode env var.
class AppMode(str, Enum):
    DEMO = "demo"
    CONNECTED = "connected"


_raw_app_mode = (os.environ.get("APP_MODE") or "").strip().lower()
try:
    APP_MODE = AppMode(_raw_app_mode) if _raw_app_mode else AppMode.DEMO
except ValueError:
    raise ValueError(
        f"Invalid APP_MODE={_raw_app_mode!r}. Allowed values: "
        f"{', '.join(m.value for m in AppMode)}; unset defaults to 'demo'."
    ) from None
```

(Place `from enum import Enum` next to the existing `import os`, then run `.venv/bin/ruff check --fix app/config.py` so ruff settles the exact import order itself.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: all pass (the pre-existing tests in the file too — the reload fixture restores state).

- [ ] **Step 5: Lint the touched files, then run the unit suite**

Run: `.venv/bin/ruff check app/config.py tests/unit/test_config.py` → expected: no new errors.
Run: `make test-unit` → expected: all pass (~148 tests).

- [ ] **Step 6: Startup smoke matrix (evidence for the report)**

```bash
APP_MODE= .venv/bin/python -c "from app import config; print(config.APP_MODE)"          # → AppMode.DEMO
APP_MODE=demo .venv/bin/python -c "from app import config; print(config.APP_MODE)"      # → AppMode.DEMO
APP_MODE=connected .venv/bin/python -c "from app import config; print(config.APP_MODE)" # → AppMode.CONNECTED
APP_MODE=garbage .venv/bin/python -c "from app import config" ; echo "exit=$?"          # → ValueError traceback, exit=1
```

Record all four outputs in the task report.

- [ ] **Step 7: Commit**

```bash
git add app/config.py tests/unit/test_config.py
git commit -m "Add typed APP_MODE config value (demo|connected, default demo)"
```

---

### Task 2: Forward `APP_MODE` in both explicit deploy paths

**Files:**
- Modify: `scripts/deploy.sh` (env-var block, lines 209-213)
- Modify: `scripts/deploy_ae_inline.py` (`env_vars` dict, lines 304-308)

**Interfaces:**
- Consumes: the env var name `APP_MODE` and default `"demo"` from Task 1 (string level only — deploy scripts don't import `app.config`).
- Produces: nothing downstream; Task 3 documents what these scripts now forward.

- [ ] **Step 1: `scripts/deploy.sh` — add the forward**

After the existing line `GCLOUD_ARGS="$GCLOUD_ARGS --set-env-vars=GOOGLE_CLOUD_LOCATION=$VERTEX_AI_LOCATION"` (line 213), add:

```bash
GCLOUD_ARGS="$GCLOUD_ARGS --set-env-vars=APP_MODE=${APP_MODE:-demo}"
```

- [ ] **Step 2: `scripts/deploy_ae_inline.py` — add the forward**

In the `env_vars` dict (lines 304-308), add one entry after `"GCS_BUCKET": args.bucket,`:

```python
            "APP_MODE": os.environ.get("APP_MODE", "demo"),  # Phase 6: inert until Phase 11/12
```

(`import os` already exists at the top of the script — verify, don't duplicate.)

- [ ] **Step 3: Verify the Cloud Run path by dry-run inspection (no deploy)**

Run: `bash scripts/deploy.sh --dry-run | grep -- "APP_MODE"`
Expected output contains: `--set-env-vars=APP_MODE=demo`
Also run: `APP_MODE=connected bash scripts/deploy.sh --dry-run | grep -- "APP_MODE"` → contains `APP_MODE=connected`.
(If `--dry-run` exits early because gcloud isn't configured in this environment, report exactly what it printed — the phase's validation asks for the generated command, so state what you observed rather than substituting a plain grep of the script; flag it as a concern if the dry-run never reached the command echo.)

- [ ] **Step 4: Verify the Agent Engine path by inspection (no deploy)**

Run: `grep -n "APP_MODE" scripts/deploy_ae_inline.py`
Expected: exactly one hit inside the `env_vars` dict.
Run: `.venv/bin/python -c "import ast,sys; tree=ast.parse(open('scripts/deploy_ae_inline.py').read()); print('parses OK')"`
Expected: `parses OK` (guards against a syntax slip in a script with no test coverage).

- [ ] **Step 5: Run the unit suite (hook parity)**

Run: `make test-unit`
Expected: all pass, unchanged — these are script-only edits.

- [ ] **Step 6: Commit**

```bash
git add scripts/deploy.sh scripts/deploy_ae_inline.py
git commit -m "Forward APP_MODE in Cloud Run and Agent Engine deploy paths"
```

---

### Task 3: Documentation (CLAUDE.md, SETUP_INSTRUCTIONS.md, DEPLOYMENT.md)

**Files:**
- Modify: `CLAUDE.md` (Environment section, line 68)
- Modify: `SETUP_INSTRUCTIONS.md` (Optional env block ~line 40-43; Version 2 workstream notes section ~line 97)
- Modify: `DEPLOYMENT.md` (Optional env-vars table ~line 338-343)

**Interfaces:**
- Consumes: names/semantics from Tasks 1-2 (env var `APP_MODE`, values `demo|connected`, default demo, ValueError on invalid, forwarded by both scripts). No code.

- [ ] **Step 1: `CLAUDE.md` — extend the Environment paragraph**

In the `## Environment` section, the current paragraph ends with `Vars go in \`app/.env\`.` Append one sentence to that same paragraph, matching its prose style:

```
Optional: `APP_MODE=demo|connected` (default `demo`; empty counts as unset; any other value fails startup with a `ValueError` at config load) — inert until Phase 11 wires provider selection, and deliberately the only user-facing mode knob.
```

- [ ] **Step 2: `SETUP_INSTRUCTIONS.md` — Optional block + workstream note**

In the `**Optional:**` env block (currently just the Maps key), add a line:

```
APP_MODE=demo                          # or connected; default demo — inert until Phase 11/12
```

In the `## Version 2 workstream setup notes` section, append a bullet after the Phase 1/5 entries:

```
- **Phase 6 (workstream 06):** `APP_MODE=demo|connected` exists as a typed config value (`app/config.py`), default `demo`; invalid values fail startup with a `ValueError`. Nothing consumes it yet — Phase 11a resolves it to a data-provider selection internally (it stays the only user-facing mode knob). Both explicit deploy paths forward it (`scripts/deploy.sh` via `--set-env-vars`, `scripts/deploy_ae_inline.py` via its `env_vars` dict); `scripts/deploy_ae.sh` picks it up from `app/.env` automatically.
```

- [ ] **Step 3: `DEPLOYMENT.md` — Optional table row**

In the `### Optional` env table (after the `GOOGLE_CLOUD_LOCATION` row), add:

```
| `APP_MODE` | `demo` (default) or `connected`; forwarded by both deploy scripts, inert until Phase 11/12 |
```

- [ ] **Step 4: Verify no forbidden files were touched**

Run: `git status --porcelain`
Expected: only `CLAUDE.md`, `SETUP_INSTRUCTIONS.md`, `DEPLOYMENT.md` modified. `git diff --stat` must NOT list `README.md` or `DEMO_GUIDE.md`.

- [ ] **Step 5: Full suite**

Run: `make test`
Expected: all pass, unchanged (docs-only task; this is the phase's "zero behavior change" validation run).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md SETUP_INSTRUCTIONS.md DEPLOYMENT.md
git commit -m "Document APP_MODE across environment and deployment docs"
```
