# Phase 13 — Production Hardening for Live Mode

## Goal

Close the gaps that are acceptable for an internal demo but not for a real, externally-facing `APP_MODE=connected` deployment talking to real BlueZoo/PoS credentials and real store data. This is the gate before calling anything a "production launch."

## Scope split (correction from review — the first draft bundled too much into one gate)

This phase is split into two tiers. **Tier A is the actual connected-mode launch gate** — the minimum that must be true before any `APP_MODE=connected` deployment is exposed beyond a developer's own machine. **Tier B is governance/operability work** that matters but shouldn't block launch on an experimental primitive or an unresolved policy conversation. Note that minimum live-secret handling (reading credentials from a real secret store, defaulting to authenticated-only deployment) was already moved into Phases 11/12 themselves per their own corrections — this phase builds the *remaining* gate items on top of that baseline, it doesn't introduce secret handling from scratch here.

## Current state (confirmed gaps — corrected against what's actually in the scripts)

- **Correction from review:** `scripts/deploy.sh`'s actual user-facing override is a `--private` flag (its case arm is at `scripts/deploy.sh:93`), not `--allow-unauthenticated`/`--no-allow-unauthenticated` as the first draft of this phase claimed — those are not user-facing *script* flags; the script constructs those exact `gcloud` args internally at `scripts/deploy.sh:234`/`:236` from whatever the `--private` flag resolves to. Verify the exact current flag names and default before writing the fix, don't assume the names above are still current by the time this is implemented.
- `app/storage.py:355-370` (`get_public_url()`) — returns unsigned, permanently-public GCS URLs. Product/video assets have no access control once uploaded.
- **Correction from review:** `activate_video()` (def at `app/tools/review_tools.py:111`) is not starting from zero — `campaign_videos` already stores `activated_at` and `activated_by` (`app/database/db.py:128-129`; `:127` is the status column), and `get_video_details()` (def at `review_tools.py:778`) already returns both (returned fields at `:885-886`). The actual gap is that `activated_by` is free-text with no real identity/auth behind it, and there's no *append-only* log of activation history (just a mutable current-state field) — describe the needed change as "add real identity + an append-only, source/mode-tagged audit log," not "build an audit trail from scratch."
- **Correction from review — IAM claim was wrong:** signing GCS URLs requires the `iam.serviceAccounts.signBlob` permission (commonly granted via `roles/iam.serviceAccountTokenCreator`), which is separate from object read/write access. `roles/storage.objectAdmin` (already granted per this repo's existing Agent Engine setup notes in `CLAUDE.md`) does **not** by itself grant signing — document both requirements, don't assume the existing role is sufficient.
- `scripts/deploy_ae.sh:248` — `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` currently exists only as a documentation comment, not an enforced setting.
- **Correction from review — ADK version/primitive claims need a spike, not an assumption.** This checkout has no installed `google-adk`/`google-genai` environment and no lockfile (`app/requirements.txt:9` is `google-adk>=1.21.0`, an unpinned lower bound; line 8 is a comment). `SecretManagerClient` is now confirmed against official docs to live at `google.adk.integrations.secret_manager.secret_client.SecretManagerClient`, requiring `google-adk >= 1.29.0` (above the current 1.21.0 floor, so a floor bump is needed) plus the `google-adk[extensions]` install extra. The exact signatures of `require_confirmation=True`/`request_confirmation()` remain unverified against a pinned version — still treat Tool Confirmation as needing a short implementation-time spike against the chosen, pinned ADK version before committing code to it, and re-verify the Secret Manager import path/signature at that time too. If direct use of Google Secret Manager's own client is simpler than ADK's wrapper, prefer that instead of forcing an ADK-specific abstraction.

## Tier A — connected-mode launch gate (do this before any shared `APP_MODE=connected` deployment)

1. Confirm the actual current deploy-script flag (see correction above) and change the default so `APP_MODE=connected` deployments require authentication unless explicitly overridden — verify against the live script, not the names in an earlier draft of this doc.
2. Move to signed, time-limited URLs for any asset served via `get_public_url()` when `APP_MODE=connected` — confirm the deploying service account has both object access and `iam.serviceAccounts.signBlob` (or `roles/iam.serviceAccountTokenCreator`), not just `roles/storage.objectAdmin`.
3. Replace `activate_video()`'s free-text `activated_by` with real caller identity — however this app's ADK deployment surfaces an authenticated user/session identity (check what Cloud Run/Agent Engine's request context actually exposes; do not invent an auth system from scratch if one already exists at the platform layer).
4. Add an append-only, identity-and-mode-tagged activation audit log (extending, not replacing, the existing `activated_at`/`activated_by` fields) — who activated which video, when, in which `APP_MODE`, from which source. This is additive to what already exists, not new from zero.

## Tier B — governance/operability enhancements (important, but not a launch blocker)

5. Enforce (not just document) whatever OTel message-content-capture policy is decided for connected mode, once that policy conversation with the client/legal actually concludes (see open questions) — either set it explicitly in the deployment scripts or explicitly disable it. Don't block Tier A on this conversation finishing.
6. Spike ADK's Secret Manager integration and/or Tool Confirmation primitive (`require_confirmation=True`/`request_confirmation()`) against a specific pinned `google-adk` version before adopting either — both are real ADK features, but neither has been verified against this repo's actual dependency floor, and Tool Confirmation is explicitly experimental. Don't let an unverified or experimental primitive block Tier A's simpler, explicit-parameter approach to activation confirmation if the spike doesn't land cleanly.
7. Richer audit-log querying (beyond "does an entry exist") — a UI or tool for reviewing activation history — is a nice-to-have on top of Tier A's append-only log, not required for launch.

## Validation

- [ ] A fresh `APP_MODE=connected` Cloud Run deployment is not publicly reachable without authentication by default (Tier A).
- [ ] Asset URLs served in connected mode are signed/time-limited, not permanently public, and the deploying service account's IAM roles are verified to include signing permission, not just object access (Tier A).
- [ ] `activate_video()` in connected mode records a real, verifiable identity, not an arbitrary caller-supplied string (Tier A).
- [ ] An append-only activation audit log entry exists and is queryable for every activation performed in connected mode, tagged with `APP_MODE` and source (Tier A).
- [ ] A pinned `google-adk` version is chosen and its Secret Manager/Tool Confirmation APIs are verified via a spike before being adopted (Tier B) — record the actual verified version and import paths used.
- [ ] Full `make test` suite (including any new auth/security-focused tests) passes.

## Exit criteria

**Tier A alone** is the gate for calling a connected-mode deployment production-ready: authenticated by default, signed/time-limited asset URLs with verified IAM roles, real-identity activation with an append-only audit log. Tier B items improve governance/operability over time and can land after launch.

## Dependencies

Phases 11b, 12 (this phase hardens the connected-mode paths those phases build).

## Open questions

1. What does authenticated-user identity actually look like on this app's deployment target (Cloud Run vs. Agent Engine) — is there an existing platform-level identity/session mechanism to build on, or does one need to be added?
2. Does BlueZoo/legal have a specific data-governance requirement around OTel message-content capture that should drive Tier B step 5's decision, rather than this plan guessing at a default? [global #13 in `99-open-questions.md`]

> **Amended (workstream bluezoo-live-verification, 2026-07-25) — the connected-mode config surface is per-tenant, which this phase's hardening must account for.** The live scan (`working-docs/bluezoo-live-verification/findings.md`) proved that a BlueZoo deployment is identified by more than a credential: the **cluster base URL varies per customer** (a valid key returns `BAD_TOKEN` against another cluster's host, so a misconfigured URL is indistinguishable from a bad credential at the call site), and **table entitlements vary per account**. Two consequences for this phase:
>
> - **Tier A, secret handling:** whatever secret store Phases 11/12 adopt holds a `{base_url, access_key}` *pair* per tenant, not a lone key. Treat the base URL as configuration that travels with the credential — separating them is how a support ticket becomes "auth is broken" when it's actually "wrong host."
> - **Tier A, error surfacing:** the fail-closed error required by Phase 11 step 4 should distinguish *bad credential* from *wrong cluster* where the API permits (both currently surface as `BAD_TOKEN`) — at minimum, name the base URL in the error text so the ambiguity is visible to whoever reads the log.
>
> No new Tier A/Tier B item is added; this is a constraint on how the existing secret-handling and error-path items are built. Note also that the tenant available today has zero rows, so any connected-mode smoke test written for this phase must treat an empty result as success, not as a failed integration.
>
> **Amended again (same workstream, 2026-07-27) — a metered quota makes this an operability concern, and adds one Tier B item.** A second tenant with real data (Morpheus / MO_92) revealed that BlueZoo meters `run_query` against a **monthly bytes-scanned allowance** — undocumented, with **no endpoint to check remaining consumption**, and **total** when exhausted: every warehouse query fails until it resets, while metadata and the Real-time API keep working. We exhausted the 1 GB/sensor-location default with ~735 MB of full-history aggregates. **BlueZoo has since clarified (2026-07-27) that the quota is an abuse guard, not a billing meter, that it is per-tenant configuration, and that they will raise it on request — MO_92 now sits at 500 GB per sensor location.** So this is an operability concern to handle, not a capacity ceiling to design around. Details: `working-docs/bluezoo-live-verification/findings.md` Part 5.1.
>
> - **Tier B (new): treat allowance exhaustion as a first-class operational state.** It is not a transient 5xx and retry makes it worse. A connected-mode deployment needs it distinguished in logs/alerts from auth failure and from an empty result, plus a documented runbook — and because the ceiling is negotiable, that runbook's first step is *ask BlueZoo to raise it*, not *wait for the month to roll over*. Since consumption cannot be queried, the app should **meter its own** estimated bytes scanned per tenant and warn before the wall; client-side accounting is the only visibility available, and it stays useful at any ceiling. `scripts/bluezoo_probe.py` models the distinction (`QuotaExceeded`) and the estimation (`row_width_bytes`); reuse rather than reinvent.
> - **Tier A, error surfacing (extends the bullet above):** the three states a connected-mode operator must be able to tell apart are now *bad credential*, *wrong cluster*, and *quota exhausted* — the first two both surface as `BAD_TOKEN`, and the third as an HTTP 400.
> - **Smoke tests:** the zero-rows caveat above still holds for AP_599, and a new one joins it — a connected-mode smoke test runs on every deploy, so it must not be broad enough to make a dent in a customer's allowance when repeated. Keep it to a single narrow, explicitly-columned query.

> **Amended (workstream 11b, 2026-07-28) — two corrections: Tier A is not blocked on Phase 12, and connected mode scans BlueZoo on every restart.**
>
> **1. The Dependencies line above over-blocks this phase.** It reads "Phases 11b, 12," but **none of Tier A's four items touch PoS or revenue**: they are deploy-time auth defaults (1), signed asset URLs (2), real activation identity (3), and the append-only activation audit log (4). Items 3 and 4 are independent of *both* live adapters. With **11b merged (`e30394f`), Tier A is startable now** and should not wait on open questions 3/4. Read the dependency as **Tier A: Phase 11b. Tier B: 11b, and 12 for anything touching the revenue path.** If Phase 12 later introduces new credential or asset surfaces, revisit items 1–2 incrementally rather than deferring the whole gate.
>
> **2. Connected mode issues a BlueZoo scan on every process start — not once per deployment.** Workstream 11b discovered that `app/database/mock_data.py`'s Step 4 regenerates metrics *unconditionally* at startup, so a misconfigured connected deployment **fails fast at boot** (good — fail-closed, and a health check catches it) while a correctly-configured one **runs a live warehouse read every restart**. Operational consequences for this phase:
>
> - **Restart frequency is now a cost driver.** Autoscaling, crash-loops and rolling deploys each multiply warehouse reads. A crash-looping connected revision could burn a meaningful slice of a tenant's monthly allowance unattended — which is exactly the scenario Tier B's client-side metering item exists for, and this is its concrete motivation rather than a hypothetical.
> - **Tier A item 1 (deploy defaults) inherits a sequencing requirement:** because startup fails closed on missing config, the `{base_url, access_key}` pair must be injected *before* the container starts, not fetched lazily on first request. Verify the deploy path satisfies this — a secret mounted after boot is indistinguishable from a missing one.
> - **Alerting must separate "failed at boot" from "failed in flight."** The former is a config/rollout problem; the latter is a credential, cluster or quota problem. See the three-state error requirement in the amendment above.
>
> Record: `working-docs/11-live-bluezoo-adapter-conformer/WORK_LOG.md` (DISCOVERY, 2026-07-28); operator-facing note in `SETUP_INSTRUCTIONS.md`.
