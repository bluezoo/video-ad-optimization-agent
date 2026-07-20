# Phase 6 — `APP_MODE` Config Value

> **Amended (workstream replan-data-track, 2026-07-16):** two clarifications after the sibling-repo reassessment. (1) **`APP_MODE` is the only user-facing mode knob.** The donor repo (`ad-campaign-agent`) selects data backends via its own `AUDIENCE_PROVIDER` env var; when Phase 11a ports that provider seam, `APP_MODE` *resolves internally* to a provider selection (`demo` → the synthetic/in-memory provider, `connected` → the live provider) — we do not adopt a second user-facing env var fighting over the same decision. (2) The step-4 protection of `populate_mock_data()`'s unconditional import-time call is **per-phase scoping, not a permanent invariant**: Phase 15 (`15-product-onboarding.md`) deliberately replaces it with explicit, idempotent, gated seeding so a from-scratch (empty-catalog) start is possible.

## Goal

Introduce a typed `APP_MODE=demo|connected` config value that Phases 11/12 will branch on, with **no behavior change in this phase**.

## Correction from review: this phase is scoped down from its first draft

The first draft of this phase also specified a bespoke `require_connected_adapters()` "fail closed" guard helper that would raise `NotImplementedError` for `APP_MODE=connected` until Phases 11/12 landed. Review correctly flagged this as abstraction without value: it's a helper Phases 11/12 immediately replace with the real thing, built before there's any real caller to protect (the app has exactly one concrete data path today, initialized unconditionally at import time in `app/agent.py:111`). Building a temporary guard for a code path that doesn't exist yet is the kind of over-engineering this plan's philosophy explicitly warns against.

**Corrected scope:** this phase adds *only* the typed config value. The actual fail-closed behavior (a real error when `APP_MODE=connected` is requested but a specific adapter isn't wired up) is built in Phase 11/12 themselves, at the actual point where a provider is selected (a factory function those phases introduce) — because that's the first point in the codebase where there's anything concrete to guard.

## Current state

No mode concept exists today. The app always uses mock/demo data (`app/database/mock_data.py`, `populate_mock_data()`, called unconditionally at import time in `app/agent.py:111`), and there is no toggle, flag, or config value anywhere that distinguishes "demo" from "would talk to a real data source." `scripts/deploy.sh` (checked directly) does not forward any `APP_MODE`-like variable today — it forwards a fixed set of other env vars (around `scripts/deploy.sh:209`), so deployment-side wiring is also new work, not an existing gap to preserve.

## Steps

1. Add `APP_MODE` to `app/config.py`, read from the environment, with a validated set of allowed values (`"demo"`, `"connected"`). Semantics, stated precisely (the first draft of this phase worded this contradictorily): **unset → `"demo"`. Set to `"demo"` → `"demo"`. Set to `"connected"` → `"connected"` (even though nothing consumes it yet in this phase). Set to anything else → raise at config-load time, app fails to start.** There is no scenario in which an invalid value silently becomes `"demo"` — invalid values are a startup error, not a silent downgrade.
2. Define a small `AppMode` enum or `Literal["demo", "connected"]` type rather than a bare string, so callers get type-checking/autocomplete instead of comparing against string literals scattered through the codebase.
3. Do not add any guard/factory helper in this phase — there is nothing yet for it to guard. `APP_MODE=connected` is valid config in this phase but has zero effect on runtime behavior; Phase 11 is where a real provider-selection factory is introduced and where `APP_MODE=connected` first does something (per that phase's own fail-closed requirement for missing credentials).
4. Do not change `populate_mock_data()`, `app/agent.py:111`'s unconditional import-time initialization, any tool in `app/tools/`, or any agent instruction **in this phase**. (Scoping note per the 2026-07-16 amendment: this is not a permanent protection — Phase 15 replaces the unconditional import-time seed with explicit, gated seeding. In this phase it simply isn't touched.)
5. Document `APP_MODE` alongside the existing environment variables. **Correction: there is no environment section in `README.md`** — the current environment documentation lives in this repo's `CLAUDE.md` (see its "Environment" section). Add `APP_MODE` there, matching the existing `GOOGLE_GENAI_USE_VERTEXAI` documentation style.
6. Update `scripts/deploy.sh` to forward `APP_MODE` to the deployed environment (it does not today), so a `connected`-mode deployment is actually possible once Phase 11/12 exist — even though this phase itself has nothing for that value to do yet.

> **Amended (workstream 06, 2026-07-18):** kickoff research found `scripts/deploy.sh` is only one of three deploy paths. `scripts/deploy_ae_inline.py` (`make deploy-ae-global`, the primary Gemini-3 path per CLAUDE.md) has its own hardcoded `env_vars` dict (~line 304) that also does not forward `APP_MODE` — owner decided this phase wires **both** explicit paths. `scripts/deploy_ae.sh` needs no change (`adk deploy agent_engine` reads `app/.env`). The `agent_engine_app.py` force-set workaround for Agent Engine's env-var dropping (DEPLOYMENT.md) is deferred to Phase 11/12, when `connected` first has runtime effect.

## Validation

- [ ] `APP_MODE` unset → app behaves exactly as it does today, confirmed by running the full existing test suite unchanged.
- [ ] `APP_MODE=demo` explicitly set → identical behavior to unset.
- [ ] `APP_MODE=connected` set → app starts successfully (no guard exists yet to block it) and every existing tool continues to use the same demo data path as before — this phase makes the value readable, not yet actionable.
- [ ] `APP_MODE=garbage` (invalid value) → app fails fast at config-load time with a clear error, not a runtime `KeyError`/`AttributeError` somewhere downstream.
- [ ] `scripts/deploy.sh` forwards `APP_MODE` to the deployed environment — verify by inspecting the generated deploy command/manifest, not just reading the script.
- [ ] `make test` passes unchanged (this phase adds tests but changes zero existing behavior).

## Exit criteria

`APP_MODE` exists as a typed, validated config value, defaults to demo, is forwarded by the deploy script, and is documented in `CLAUDE.md` — with no other behavior change. The fail-closed guard is explicitly deferred to Phase 11/12, not built here.

## Dependencies

None.

## Open questions

None — this is a well-understood config pattern, not a design decision requiring the client's input.
