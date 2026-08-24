# Workstream: omni-edit-routing-and-quality

**Branch:** version_2_omni-edit-routing
**Base:** version_2 @ 7be6519 (post-ws14c merge)

Not tied to a numbered `.docs/version2-plan/` phase doc — a same-day
follow-up fix discovered via owner-directed live testing of ws14c's
newly-deployed `edit_video_with_omni` tool against a fresh Agent Engine
deployment in `document-ai-test-337818`.

## 2026-08-23 — kickoff: live testing surfaced 4 issues

Owner ran manual queries against the live deployment; asked to run edit
queries myself, verify the journey end-to-end, and catalog every issue for
one batched fix. Found:
1. `ENABLE_OMNI_EDIT` was missing entirely from `deploy_ae_inline.py`'s
   `env_vars` dict — the flag was never on in the deployed container.
2. Agent Engine deploys a pickled Python object built by importing
   `app.agent` locally; module-level `os.environ.get(...)` constants (like
   `ENABLE_OMNI_EDIT`) are frozen at local deploy-time, not re-read from the
   container's `env_vars` at request time. Fixing (1) alone via `update()`
   with only `env_vars=` did nothing — required re-importing `app.agent`
   with the flag set locally, then passing a fresh `agent_engine=` object to
   `update()`.
3. `403 PERMISSION_DENIED: aiplatform.interactions.create` in
   `document-ai-test-337818` — not fixable via `roles/aiplatform.user`,
   `.admin`, or `.editor` (granted Editor to test, no effect, reverted).
   Permission doesn't appear in `gcloud iam list-testable-permissions` for
   either test project. Working hypothesis: Omni Interactions API (Preview)
   is gated by a project allowlist outside standard IAM. **Deferred —
   escalation/allowlist request needed, out of scope for this workstream.**
4. Natural-language routing gap: free-form "edit the video" phrasing never
   reached `edit_video_with_omni`, because only `REVIEW_AGENT_INSTRUCTION`
   mentioned the tool — Coordinator and Media Agent had zero awareness of
   it, so the LLM routed such requests to Media Agent's full Veo
   regeneration instead. **Owner directed: fix this one first, test locally,
   owner reviews before merge.**

## 2026-08-23 — Issue #4 fixed: edit-vs-generate routing

`app/agent.py`, all changes gated `if ENABLE_OMNI_EDIT:` (flag-off behavior
byte-identical, verified by test):
- New section appended to `MEDIA_AGENT_INSTRUCTION`: edit/tweak requests on
  an existing video are Review Agent's job, not Media Agent's; only
  generate a new video from scratch.
- `media_agent`'s `description=` gains "does NOT edit existing videos."
- `REVIEW_AGENT_INSTRUCTION`'s existing omni-edit section gains an explicit
  bullet: on a same-turn/follow-up "apply that edit" confirmation, call
  `edit_video_with_omni` directly — do NOT transfer back to Media Agent.
- `review_agent`'s `description=` gains explicit edit-handling language.
- New section appended to `COORDINATOR_INSTRUCTION`: edit requests route to
  Review Agent, new-video requests route to Media Agent.

Added two guard tests to `tests/unit/test_agent_instructions.py` (mirroring
the existing review_agent flag pattern):
`test_routing_instructions_unchanged_when_omni_edit_disabled` and
`test_routing_instructions_mention_edit_handoff_when_enabled`.

Verified locally via `adk web` (this worktree, `ENABLE_OMNI_EDIT=true` in
`app/.env`) against two previously-broken live scenarios:
- Free-form mid-Media-Agent-conversation edit request → Media Agent now
  correctly `transfer_to_agent("review_agent")` instead of generating a new
  video.
- Review table → id-based edit → follow-up "yes, apply that" → Review Agent
  calls `edit_video_with_omni` directly, no deflection to Media Agent.

`make lint` clean; `tests/unit` 422 passed/1 skipped; `tests/e2e` 25
passed/1 skipped.

## 2026-08-23 — Veo generation quality fix (owner-directed follow-up)

Owner reported Omni-edited video quality looked "slightly bad" and asked to
verify Veo/Omni Flash model versions and generation parameters against
current docs.

Findings:
- `VIDEO_GEN_MODEL=veo-3.1-generate-001` and `OMNI_EDIT_MODEL=gemini-omni-flash-preview`
  (`app/config.py`) are both correct/current model IDs.
- All 3 `GenerateVideosConfig(...)` call sites in `app/tools/video_tools.py`
  left `resolution`, `compression_quality`, and `generate_audio` unset,
  silently defaulting to 720p/OPTIMIZED — confirmed via the installed
  `google-genai` 2.19.0 SDK's field list and docs research.
- Gemini Omni Flash's `im.VideoConfig` exposes only a `task` field — no
  resolution/quality knob exists on that side at all; its video-edit output
  is capped at ~720p during public preview regardless of source quality.
  Confirmed empirically (see below) — not a gap in our config.

Fix: added `resolution="1080p"` and `generate_audio=True` to all 3
`GenerateVideosConfig` call sites. Also tried `compression_quality=LOSSLESS`
first — reverted after live testing showed it fails outright at *any*
resolution (`"Generated video is large, an output storage uri is required"`)
because our pipeline expects inline video bytes, not a GCS-URI output; not
worth the larger plumbing change for this fix's scope.

Live verification (real Vertex calls, via local `adk web`, ffprobe on
downloaded output):
- Old (pre-fix) generated video: 720×1280, ~10.2 Mbps, 10.4 MB (8s).
- New (fixed) generated video (id 15): **1080×1920, ~25.9 Mbps, 26.1 MB (8s)**.
- Omni edit of the OLD 720p source (id 14): 1280×720, ~1.97 Mbps, 2.11 MB.
- Omni edit of the NEW 1080p source (id 16, from id 15): 720×1280, ~1.93
  Mbps, 2.07 MB — **no measurable improvement**, confirming Omni Flash's
  preview ceiling is independent of source quality. Documented explicitly
  for the owner rather than oversold as a full fix.

`make lint` clean; `tests/unit` 422 passed/1 skipped; `tests/e2e` 25
passed/1 skipped (no test asserted on exact `GenerateVideosConfig` kwargs,
so no test changes needed for this fix).

## 2026-08-24 — owner reviewed and approved both fixes locally

Owner manually tested both fixes against local `adk web` (port 8501, this
worktree). One unrelated blocker hit mid-testing: local `gcloud`
Application Default Credentials required interactive re-auth (Google
Workspace RAPT/reauth policy on the account used for local ADC, not a code
issue) — resolved by the owner re-running
`gcloud auth application-default login` and restarting the dev server.
Owner confirmed the routing fix and Veo quality fix both work as intended.

## 2026-08-24 — checkpoint: finish
