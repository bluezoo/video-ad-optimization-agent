# Workstream 14c: omni-video-editing

**Branch:** version_2_omni-video-editing
**Phase doc:** .docs/version2-plan/14c-omni-video-editing.md

## Research findings

Phase doc claims re-verified against current code (2026-08-23):

- `app/requirements.txt:26` — `google-genai>=1.55.0` confirmed as the current unpinned floor; needs bumping to `>=2.14.0` (the version every successful live Interactions probe, 14b's and this session's, actually used).
- `app/agent.py:521-539` — `review_agent` (`LlmAgent`) confirmed as the sole home for HITL review/activation tools (`get_video_review_table`, `get_video_details`, `list_pending_videos`, `activate_video`, `activate_batch`, `pause_video`, `archive_video`, `get_video_status`, `get_activation_summary`, `generate_additional_metrics`) — no edit/revision tool exists today, confirming the phase doc's gap claim.
- `app/tools/video_tools.py:470` — `generate_video_from_product()` signature confirmed as the convention to mirror (async, dict return). Three `client.models.generate_videos()` call sites confirmed at lines 362, 639, 998 (phase doc's 14b-era line numbers had drifted slightly but the three-call-site claim holds).
- `app/config.py:95-97` — confirms the exact env-var/default pattern (`os.environ.get("X_MODEL", "default")`) and that `VIDEO_GEN_MODEL`'s own comment already anticipates this ("possibly Omni later"). `BLUEZOO_VALID_POLICY` (lines 72-84) is the most recent precedent for an enum-style feature flag with fail-loud validation — `ENABLE_OMNI_EDIT` will follow the simpler boolean-flag pattern instead (no enum needed, just on/off).
- All capability claims in the phase doc (Omni Flash reachability, the two undocumented API contract details, the confirmed-broken translation/dubbing finding) come from this session's own live-tested exploration (Veo3 test-video generation, a live edit-task call verified by frame-diff, a live translation-task call verified by transcript+lip-sync judgment) — not re-derived here, since they're first-party live evidence from earlier this same session, not documentation claims that could have drifted.

No stale claims found; nothing needed correcting beyond the phase doc's own already-current state.

## Implementation approach

As specified in the phase doc's "Implementation approach" section: a new `app/tools/video_edit_tools.py` module exposing `edit_video_with_omni(video_id, edit_instruction, *, max_wait_time=300) -> dict`, registered as a new tool on the existing `review_agent` (not a new Edit Agent), gated behind `ENABLE_OMNI_EDIT` (default off). `translate_video_dialogue()` ships as a documented `NotImplementedError` placeholder only, never wired into any agent.

**Alternative considered and rejected:** a new dedicated Edit Agent, routed to by the Coordinator. Rejected because it would duplicate the Review Agent's existing HITL context (which video is under review, DB id/lineage, activation-gating) and require a new Coordinator routing rule for a single tool — unjustified complexity for one opt-in capability. Revisit only if edit-related tools multiply later (a real dubbing backend, multi-step edit chains, edit-history browsing).

**Alternative considered and rejected:** sharing a polling helper between Veo's `_wait_for_veo_operation` and the new Omni interaction-polling logic. Rejected per 14b's own already-recorded finding — operations and interactions are different primitives (`client.operations.get()` vs `client.interactions.get()`), and forcing one shared helper would be the wrong abstraction boundary.

## Test plan

- **Unit (fast tier, network-free):** `tests/unit/test_video_edit_tools.py` — stub/mock the Omni interactions client (parallel to how `tests/unit/test_live_bluezoo_datasource.py`'s companion fast-tier tests override the sole networked method in ws11b). Cover: success path, timeout, `interactions.get` 500-on-sync-id handling, the two contract-detail guards (`pathlib.Path` wrapping, no `aspect_ratio` on edit tasks) — assert the guards are applied, not just documented in a comment.
- **Live tier:** `tests/live/test_omni_video_edit.py`, `pytest.mark.live`, part of `make test-live`. One real end-to-end call: edit a real pipeline-generated video (not a throwaway clip) with a single-attribute instruction, assert success + a plausible output (duration/codec match, non-trivial file size) — mirrors ws11b's `tests/live/test_live_bluezoo_datasource.py` shape.
- **Demo scenario:** extend `docs/demo-scenarios/fashion.md` with one new scene driving `edit_video_with_omni` through `adk web`, verified via `verifying-with-demo-scenarios` + the `demo-scenario-verifier` subagent — a real edit request against a real reviewed video, confirming the tool call fires with sane arguments and the response references the edited artifact's `source_video_id` lineage. Re-run the existing fashion scenarios in the same pass to confirm `ENABLE_OMNI_EDIT=false` (default) leaves them byte-identical.
- Add the journey to root `DEMO_GUIDE.md`'s "Workstream Testing Journeys" section per CLAUDE.md's ws11a rule.

## Out of scope

Same as the phase doc's "Out of scope" section, restated for the approval gate:
- EN→ES (or any) dialogue translation/dubbing/lip-sync — confirmed broken for this model; explicitly deferred by the owner ("the audio translation we can work later").
- Chained/iterative revision via `previous_interaction_id` for edit tasks.
- Multi-attribute edit instructions in a single call.
- GCS-storage-mode edits (unverified by any live probe so far — local-mode only).
- Any change to the default Veo generation pipeline or `VIDEO_GEN_MODEL`.
- Making `ENABLE_OMNI_EDIT` default-on.
