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
