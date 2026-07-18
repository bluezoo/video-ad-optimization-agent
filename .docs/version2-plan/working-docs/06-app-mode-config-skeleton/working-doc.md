# Workstream 06: app-mode-config-skeleton

**Branch:** version_2_app-mode-config
**Phase doc:** .docs/version2-plan/06-app-mode-config-skeleton.md (rated Small; dependencies: none)
**Base:** version_2 @ 49d015c (post-ws05 merge)

## Research findings

Kickoff research (2026-07-18, three parallel agents: config/runtime, deploy paths, docs/tests) re-verified every phase-doc claim against current code:

**Confirmed:**
- No `APP_MODE`/mode concept exists anywhere in `app/`, `scripts/`, `tests/`, `Makefile` — clean slate, no naming collision. (One orthogonal precedent: `app/storage.py:55-62` has a `'gcs'|'local'` storage mode derived from `GCS_BUCKET`; unrelated to demo-vs-connected data sourcing.)
- `populate_mock_data()` still called at import time at exactly `app/agent.py:111` (now inside a log-and-re-raise `try` at `:109-116` — fail-fast semantics unchanged). Post-ws05 it is create-once / regen-metrics-always; adding an unconsumed `APP_MODE` cannot affect it.
- `app/config.py` house style: flat module-level UPPER_CASE constants via `os.environ.get` (e.g. `MODEL` :24, `GCS_BUCKET` :53), derived booleans (`IS_CLOUD_RUN` :42), no typing imports, and **no existing validation that raises at import** — `APP_MODE` introduces the first.
- `scripts/deploy.sh` forwards a fixed env set via `--set-env-vars` at lines 210-213 (+ conditional Maps key at 216-225); no `APP_MODE` (doc said ~:209 — comment line; accurate).
- A raise in `config.py` genuinely surfaces at startup in every entrypoint: `app/__init__.py:17` → `app/agent.py:47` `from .config import …` (no swallowing try), and `tests/conftest.py:45` imports `app.config` at module scope, so an invalid value even fails pytest collection (fail-fast as intended).
- No environment section in `README.md`; env docs live in `CLAUDE.md` "Environment" (prose style) — confirmed.

**Drift / facts the phase doc misses:**
1. **`tests/unit/test_config.py` already exists** (created in ws01, after this phase doc was written) with exactly the needed pattern: autouse fixture doing `monkeypatch.undo()` + `importlib.reload(app.config)` per test. `APP_MODE` tests extend this file; the invalid-value test is `monkeypatch.setenv("APP_MODE","garbage")` + `pytest.raises(ValueError)` around the reload. No new test infra.
2. **Step 6 names only `scripts/deploy.sh`, but the repo has three deploy paths.** (a) Cloud Run `scripts/deploy.sh` — explicit `--set-env-vars`, needs a new flag. (b) `scripts/deploy_ae.sh` (`make deploy-ae`) — `adk deploy agent_engine` reads `app/.env` automatically, zero script change needed. (c) **`scripts/deploy_ae_inline.py` (`make deploy-ae-global`) — the primary path per CLAUDE.md's gotchas — has its own hardcoded `env_vars` dict at :304-308** that would NOT forward `APP_MODE`. `DEPLOYMENT.md:188-220` documents the repo's own "adding a new env var" procedure for that path.
3. **Error type matters:** `deploy_ae_inline.py:259` catches `ImportError` specifically (mislabeling it "run from project root") — invalid `APP_MODE` must raise `ValueError` so the failure is reported honestly.
4. **Enum house style exists:** `app/models/video_properties.py:17-87` has eight `class X(str, Enum)` types; `Literal` appears nowhere in `app/`. The phase doc's "enum or Literal" choice resolves to `class AppMode(str, Enum)` by house style.
5. **`SETUP_INSTRUCTIONS.md` also documents env vars** (its Environment section :21-43 with literal `app/.env` blocks), and its line 97 already reserves a "APP_MODE (Phase 6)" note to fill in. Step 5's "document in CLAUDE.md" extends to both files per repo convention.
6. Env-var enumerations that go stale with any new var: `DEPLOYMENT.md` managed-vars tables (:174-179, :330-350). Updating them is cheap doc accuracy.

**Amendment noted (per phase doc header + owner's kickoff instruction):** `APP_MODE` is the *only* user-facing mode knob — when Phase 11a ports the provider seam, it resolves internally to provider selection; no second env var. The step-4 protection of import-time seeding is per-phase scoping only; Phase 15 replaces it. Nothing in this workstream may foreclose either.

## Implementation approach

Single small change set, matching house style exactly:

1. **`app/config.py`:** add `class AppMode(str, Enum)` with `DEMO = "demo"`, `CONNECTED = "connected"`, then `APP_MODE: AppMode` parsed from `os.environ.get("APP_MODE", "demo")`, normalized (`.strip().lower()`), raising `ValueError` with a clear message (naming the bad value and the allowed set) on anything else. Unset → demo; `demo` → demo; `connected` → connected (readable, not yet actionable); anything else → startup failure. No silent downgrade. A short comment states the Phase 11a resolution semantics (demo → synthetic provider, connected → live provider) so the enum's future is discoverable without a second knob.
2. **No guard/factory** — per the phase doc's corrected scope, nothing consumes the value in this phase.
3. **No touch** to `populate_mock_data()`, `app/agent.py:111`, any tool, or any agent instruction.
4. **Deploy wiring — recommended scope: both explicit-forwarding paths, not just `deploy.sh`.**
   - `scripts/deploy.sh`: add `--set-env-vars=APP_MODE=${APP_MODE:-demo}` beside the existing block (:210-213).
   - `scripts/deploy_ae_inline.py`: add `"APP_MODE": os.environ.get("APP_MODE", "demo")` to the `env_vars` dict (:304-308).
   - `scripts/deploy_ae.sh`: no change (reads `app/.env`).
   - The `agent_engine_app.py` force-set workaround (Agent Engine sometimes drops `env_vars`; DEPLOYMENT.md :188-215) is **deferred to Phase 11/12** — it only matters when `connected` has runtime effect, and unset always safely means demo.
   - *Alternative considered and rejected:* wiring only `deploy.sh` (the phase doc's literal step 6). Rejected because `make deploy-ae-global` is the primary documented deploy path for the Gemini-3 models; leaving it unwired makes step 6's own stated purpose ("a connected-mode deployment is actually possible once 11/12 exist") false on the path that's actually used.
5. **Docs:** `CLAUDE.md` Environment section (one prose line in existing style: optional `APP_MODE=demo|connected`, default demo, invalid values fail startup, consumed from Phase 11 on); `SETUP_INSTRUCTIONS.md` Environment block + fill in the reserved line-97 note; `DEPLOYMENT.md` managed-vars tables.
6. **Tests** (extend `tests/unit/test_config.py`, existing reload pattern): unset → `AppMode.DEMO`; explicit `demo` → `DEMO`; `connected` → `CONNECTED`; case/whitespace normalization; `garbage` → `ValueError` at reload; and `APP_MODE` member of the enum type (not bare string).

## Test plan

- `make test` unchanged and green (the phase's own validation: zero behavior change), plus the new `test_config.py` cases above.
- Startup smoke matrix (evidence logged in WORK_LOG): `APP_MODE` unset, `=demo`, `=connected` → `python -c "import app.agent"` succeeds identically; `APP_MODE=garbage` → fails fast with the clear `ValueError`, verified for both `import app.agent` and pytest collection.
- Deploy validation without deploying: `make deploy-dry-run` (`deploy.sh --dry-run` prints the full gcloud command, :252-258) shows `APP_MODE` in `--set-env-vars`; `deploy_ae_inline.py` verified by asserting the `env_vars` dict contents (inspection/test, no real deploy).
- **Demo scenario: explicitly skipped** per `verifying-with-demo-scenarios`' allowance for genuinely non-agent-facing work — this phase changes zero tool/agent behavior, and every scenario in `docs/demo-scenarios/fashion.md` scripts agent behavior. The skip and its justification will be stated in `WORK_LOG.md` (never silently omitted), with the smoke matrix above standing in as the end-to-end startup evidence.

## Out of scope

- Any consumer of `APP_MODE`: no guard, no factory, no provider seam (Phase 11a), no fail-closed behavior (Phases 11/12).
- No second mode env var, ever (amendment: `APP_MODE` resolves internally to provider selection when 11a lands).
- No change to `populate_mock_data()` / import-time seeding (Phase 15 replaces that), tools, agent instructions, or `README.md`/`DEMO_GUIDE.md`.
- No `agent_engine_app.py` force-set workaround (deferred to Phase 11/12 with the connected-mode work).
- No real deployment as part of verification (dry-run/inspection only).
