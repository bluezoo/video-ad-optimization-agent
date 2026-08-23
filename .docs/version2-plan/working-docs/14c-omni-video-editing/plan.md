# Omni Video Editing (Phase 14c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (this repo's vendored copy in `.claude/skills/`, NOT the global `superpowers:` one — the local copy carries the WORK_LOG/STATUS conventions) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, feature-flagged `edit_video_with_omni` tool to the Review Agent that applies a single-attribute visual edit to an already-generated video via Gemini Omni Flash's Interactions API, with the default Veo pipeline and `ENABLE_OMNI_EDIT=false` behavior completely unaffected.

**Architecture:** New standalone tool module (`app/tools/video_edit_tools.py`) parallel to `video_tools.py` but with its own polling primitive (interactions, not operations — a different API surface). Registered on the existing `review_agent`, gated by a boolean config flag. A `source_video_id` DB column tracks lineage from an edited video back to its original.

**Tech Stack:** `google-genai` SDK (`google.genai.interactions` typed module, floor bumped to `>=2.14.0`), Vertex AI (`gemini-omni-flash-preview`), existing `app.storage` module for read/write of video bytes (already storage-mode-agnostic: local vs GCS).

## Global Constraints

- `google-genai` must be bumped to `>=2.14.0` in `app/requirements.txt` as its own isolated step, verified with `make test` **before** any new tool code is written — isolates SDK-upgrade risk from feature risk.
- `ENABLE_OMNI_EDIT` defaults to `false`. When false, `review_agent`'s tool list and `REVIEW_AGENT_INSTRUCTION` text must be byte-identical to their pre-this-phase state.
- Fast tier (`make test`) stays network-free: all `video_edit_tools.py` unit tests mock `client.interactions.create`/`client.interactions.get` — no real API calls.
- `VideoContent.data` must always be a `pathlib.Path` (never a bare `str` or raw `bytes`) — a live-tested contract detail; passing anything else sends corrupt base64 that only fails server-side.
- `response_format` must never set `aspect_ratio` for an edit-task call — the server derives it from the input video and 400s if it's set explicitly.
- `translate_video_dialogue()` must raise `NotImplementedError` and must never be imported into `app/agent.py` or registered as a tool.
- Do not modify `app/tools/video_tools.py`, `VIDEO_GEN_MODEL`, or any Veo call site.
- No `Co-Authored-By: Claude` or AI-attribution trailers in any commit message.

---

### Task 1: SDK bump, config flag, DB lineage column

**Files:**
- Modify: `app/requirements.txt:26`
- Modify: `app/config.py` (after line 97)
- Modify: `app/database/db.py` (campaign_videos `CREATE TABLE`, ~line 118-141; `run_migrations()`, ~line 281-330+)
- Test: `tests/unit/test_config.py`, `tests/unit/test_database.py` (or wherever existing migration tests live — see Step 2)

**Interfaces:**
- Produces: `app.config.OMNI_EDIT_MODEL: str`, `app.config.ENABLE_OMNI_EDIT: bool`, and a `campaign_videos.source_video_id INTEGER` column (nullable, FK to `campaign_videos.id`) — Task 2 reads/writes this column via raw SQL, not an ORM, matching every other column in this table.

- [ ] **Step 1: Bump the SDK floor and reinstall**

Edit `app/requirements.txt:26`:

```diff
-google-genai>=1.55.0
+google-genai>=2.14.0
```

Run in this worktree:

```bash
.venv/bin/pip install --upgrade "google-genai>=2.14.0"
.venv/bin/python -c "from google.genai import interactions; print('interactions module OK:', interactions.__file__)"
```

Expected: prints a real file path (e.g. `.../google/genai/interactions.py`), no ImportError.

- [ ] **Step 2: Regression-test the bump alone, before any new code**

```bash
make test
```

Expected: full existing fast-tier suite still green (406+ tests). If anything breaks, it's the SDK bump interacting with the existing Veo call sites (`app/tools/video_tools.py`) — fix that before proceeding to Step 3; do not proceed with a red suite.

- [ ] **Step 3: Add the two config values**

Edit `app/config.py`, immediately after line 97 (`VIDEO_GEN_MODEL = ...`):

```python
# Phase 14c: Gemini Omni Flash post-generation visual-edit tool.
# Preview/experimental model with a defined sunset (Vertex model card:
# retirement 2027-06-30) -- kept fully opt-in via ENABLE_OMNI_EDIT.
OMNI_EDIT_MODEL = os.environ.get("OMNI_EDIT_MODEL", "gemini-omni-flash-preview")
ENABLE_OMNI_EDIT = os.environ.get("ENABLE_OMNI_EDIT", "false").strip().lower() == "true"
```

- [ ] **Step 4: Write the failing config test**

Add to `tests/unit/test_config.py` (create the file if it doesn't already exist — check first with `ls tests/unit/test_config.py`; if it exists, add this test class to it following the file's existing import/reload pattern for env-driven config, e.g. how `BLUEZOO_VALID_POLICY`'s test reloads `app.config` after `monkeypatch.setenv`):

```python
class TestOmniEditConfig:
    def test_defaults_to_disabled(self, monkeypatch):
        monkeypatch.delenv("ENABLE_OMNI_EDIT", raising=False)
        monkeypatch.delenv("OMNI_EDIT_MODEL", raising=False)
        import importlib
        from app import config
        importlib.reload(config)
        assert config.ENABLE_OMNI_EDIT is False
        assert config.OMNI_EDIT_MODEL == "gemini-omni-flash-preview"

    def test_enabled_via_env(self, monkeypatch):
        monkeypatch.setenv("ENABLE_OMNI_EDIT", "true")
        import importlib
        from app import config
        importlib.reload(config)
        assert config.ENABLE_OMNI_EDIT is True
```

- [ ] **Step 5: Run it, confirm it fails without Step 3, passes with it**

```bash
pytest tests/unit/test_config.py -k OmniEdit -v
```

Expected: PASS (Step 3's code already exists at this point since these are sequential edits — if you're doing strict TDD, comment out Step 3's addition first, confirm `AttributeError`, then restore it and re-run to confirm PASS).

- [ ] **Step 6: Add the `source_video_id` lineage column**

Edit `app/database/db.py`'s `campaign_videos` `CREATE TABLE` (~line 118-141) to add the column for fresh databases:

```diff
             duration_seconds INTEGER DEFAULT 8,
             aspect_ratio TEXT DEFAULT '9:16',
             status TEXT DEFAULT 'generated' CHECK(status IN ('generating', 'generated', 'activated', 'paused', 'archived')),
             activated_at TIMESTAMP,
             activated_by TEXT,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
             generation_time_seconds INTEGER,
+            source_video_id INTEGER,
             FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
-            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
+            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
+            FOREIGN KEY (source_video_id) REFERENCES campaign_videos(id) ON DELETE SET NULL
         )
     ''')
```

Add a migration block to `run_migrations()` (same file, following the exact existing pattern at ~line 290-314 — insert after the `store_name` migration block):

```python
    # Migration N: Add source_video_id to campaign_videos (Phase 14c lineage)
    cursor.execute("PRAGMA table_info(campaign_videos)")
    video_columns = [column[1] for column in cursor.fetchall()]

    if "source_video_id" not in video_columns:
        print("[DB Migration] Adding source_video_id column to campaign_videos...")
        cursor.execute(
            "ALTER TABLE campaign_videos ADD COLUMN source_video_id INTEGER "
            "REFERENCES campaign_videos(id)"
        )
        conn.commit()
        print("[DB Migration] source_video_id column added successfully.")
```

- [ ] **Step 7: Verify the migration against a fresh test DB**

```bash
.venv/bin/python -c "
from app.database.db import init_database, run_migrations, get_connection
init_database()
run_migrations()
conn = get_connection()
cols = [r[1] for r in conn.execute('PRAGMA table_info(campaign_videos)').fetchall()]
assert 'source_video_id' in cols, cols
print('OK: source_video_id present')
"
```

Expected: prints `OK: source_video_id present`, no exception.

- [ ] **Step 8: Run the full fast suite again**

```bash
make test
```

Expected: still fully green — this step only adds a nullable column, no existing INSERT/SELECT statement should break.

- [ ] **Step 9: Commit**

```bash
git add app/requirements.txt app/config.py app/database/db.py tests/unit/test_config.py
git commit -m "feat(14c): bump google-genai floor, add Omni edit config flags + source_video_id lineage column"
```

---

### Task 2: `video_edit_tools.py` module + network-free unit tests

**Files:**
- Create: `app/tools/video_edit_tools.py`
- Test: `tests/unit/test_video_edit_tools.py`

**Interfaces:**
- Consumes: `app.config.OMNI_EDIT_MODEL`, `app.config.ENABLE_OMNI_EDIT` (Task 1); `app.storage.read_video(path_or_filename: str) -> bytes`, `app.storage.save_video(filename: str, data: bytes) -> str` (both pre-existing); `app.database.db.get_db_cursor()` (pre-existing context manager, auto-commits on success, `sqlite3.Row` row factory).
- Produces: `async def edit_video_with_omni(video_id: int, edit_instruction: str, *, max_wait_time: int = 300) -> dict` and `async def translate_video_dialogue(video_id: int, target_language: str) -> dict` (raises `NotImplementedError`) — Task 3 imports both names (the second only to confirm it stays unregistered).

- [ ] **Step 1: Write the module skeleton and failing tests together (TDD)**

Create `tests/unit/test_video_edit_tools.py`:

```python
"""Unit tests for app.tools.video_edit_tools — fully network-free: the
Omni Flash interactions client is always mocked. Live behavior against the
real API is covered separately by tests/live/test_omni_video_edit.py."""

import pytest
from unittest.mock import MagicMock, patch

from app.tools import video_edit_tools


def _fake_video_row(video_id=1):
    return {
        "id": video_id,
        "campaign_id": 1,
        "product_id": 1,
        "video_filename": "some-video.mp4",
        "duration_seconds": 8,
        "aspect_ratio": "9:16",
        "scene_prompt": "a scene",
        "status": "generated",
    }


def _completed_interaction(video_b64):
    """A minimal stand-in for a completed google.genai Interaction object."""
    content = MagicMock()
    content.type = "video"
    content.data = video_b64
    content.uri = None
    step = MagicMock()
    step.type = "model_output"
    step.content = [content]
    interaction = MagicMock()
    interaction.status = "completed"
    interaction.steps = [step]
    interaction.id = "interaction-123"
    interaction.output_video = None
    return interaction


class TestLoadVideoBytesForEdit:
    def test_video_not_found_raises(self, test_db):
        with pytest.raises(video_edit_tools.OmniEditError, match="not found"):
            video_edit_tools._load_video_bytes_for_edit(999999)


class TestEditVideoWithOmni:
    @pytest.mark.asyncio
    async def test_success_creates_new_video_row(self, test_db):
        import base64
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO campaign_videos (campaign_id, product_id, video_filename, status, duration_seconds, aspect_ratio, scene_prompt) "
                "VALUES (1, 1, 'source.mp4', 'generated', 8, '9:16', 'a scene')"
            )
            source_id = cursor.lastrowid

        fake_bytes = b"fake mp4 bytes"
        video_b64 = base64.b64encode(b"edited mp4 bytes").decode()

        with patch("app.tools.video_edit_tools.storage.read_video", return_value=fake_bytes), \
             patch("app.tools.video_edit_tools.storage.save_video", return_value="omni-edit-x.mp4") as mock_save, \
             patch("app.tools.video_edit_tools._build_client") as mock_build_client:
            mock_client = MagicMock()
            mock_client.interactions.create.return_value = _completed_interaction(video_b64)
            mock_build_client.return_value = mock_client

            result = await video_edit_tools.edit_video_with_omni(source_id, "change the shirt color to red")

        assert result["success"] is True
        assert result["source_video_id"] == source_id
        assert result["video_id"] != source_id
        assert result["backend"] == "omni_flash"
        assert result["interaction_id"] == "interaction-123"
        mock_save.assert_called_once()

        # Lineage persisted
        from app.database.db import get_db_cursor as _cur
        with _cur() as cursor:
            cursor.execute("SELECT source_video_id FROM campaign_videos WHERE id = ?", (result["video_id"],))
            row = cursor.fetchone()
        assert row["source_video_id"] == source_id

    @pytest.mark.asyncio
    async def test_missing_video_returns_error_dict(self, test_db):
        result = await video_edit_tools.edit_video_with_omni(999999, "change the color")
        assert result["success"] is False
        assert result["error_type"] == "not_found"

    @pytest.mark.asyncio
    async def test_non_completed_status_returns_unsupported_edit(self, test_db):
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO campaign_videos (campaign_id, product_id, video_filename, status, duration_seconds, aspect_ratio) "
                "VALUES (1, 1, 'source2.mp4', 'generated', 8, '9:16')"
            )
            source_id = cursor.lastrowid

        interaction = MagicMock()
        interaction.status = "failed"

        with patch("app.tools.video_edit_tools.storage.read_video", return_value=b"x"), \
             patch("app.tools.video_edit_tools._build_client") as mock_build_client:
            mock_client = MagicMock()
            mock_client.interactions.create.return_value = interaction
            mock_build_client.return_value = mock_client

            result = await video_edit_tools.edit_video_with_omni(source_id, "change the color")

        assert result["success"] is False
        assert result["error_type"] == "unsupported_edit"

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_error_type(self, test_db):
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO campaign_videos (campaign_id, product_id, video_filename, status, duration_seconds, aspect_ratio) "
                "VALUES (1, 1, 'source3.mp4', 'generated', 8, '9:16')"
            )
            source_id = cursor.lastrowid

        in_progress = MagicMock()
        in_progress.status = "in_progress"
        in_progress.id = "interaction-456"

        with patch("app.tools.video_edit_tools.storage.read_video", return_value=b"x"), \
             patch("app.tools.video_edit_tools._build_client") as mock_build_client, \
             patch("app.tools.video_edit_tools._POLL_INTERVAL_SECONDS", 0):
            mock_client = MagicMock()
            mock_client.interactions.create.return_value = in_progress
            mock_client.interactions.get.return_value = in_progress  # never reaches terminal
            mock_build_client.return_value = mock_client

            result = await video_edit_tools.edit_video_with_omni(source_id, "change the color", max_wait_time=0)

        assert result["success"] is False
        assert result["error_type"] == "timeout"


class TestTranslateVideoDialoguePlaceholder:
    @pytest.mark.asyncio
    async def test_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            await video_edit_tools.translate_video_dialogue(1, "es")


class TestContractDetailGuards:
    @pytest.mark.asyncio
    async def test_video_content_data_is_path_not_str(self, test_db):
        """Regression test for the live-discovered contract detail: a bare
        str for VideoContent.data silently sends corrupt base64 server-side.
        Assert the call site always passes a pathlib.Path."""
        import base64
        from pathlib import Path
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO campaign_videos (campaign_id, product_id, video_filename, status, duration_seconds, aspect_ratio) "
                "VALUES (1, 1, 'source4.mp4', 'generated', 8, '9:16')"
            )
            source_id = cursor.lastrowid

        video_b64 = base64.b64encode(b"edited bytes").decode()
        captured = {}

        def fake_create(**kwargs):
            content_arg = kwargs["input"][0].content[0]
            captured["data_type"] = type(content_arg.data)
            return _completed_interaction(video_b64)

        with patch("app.tools.video_edit_tools.storage.read_video", return_value=b"x"), \
             patch("app.tools.video_edit_tools.storage.save_video", return_value="out.mp4"), \
             patch("app.tools.video_edit_tools._build_client") as mock_build_client:
            mock_client = MagicMock()
            mock_client.interactions.create.side_effect = fake_create
            mock_build_client.return_value = mock_client

            await video_edit_tools.edit_video_with_omni(source_id, "change the color")

        assert captured["data_type"] is Path

    @pytest.mark.asyncio
    async def test_response_format_never_sets_aspect_ratio(self, test_db):
        import base64
        from app.database.db import get_db_cursor

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO campaign_videos (campaign_id, product_id, video_filename, status, duration_seconds, aspect_ratio) "
                "VALUES (1, 1, 'source5.mp4', 'generated', 8, '9:16')"
            )
            source_id = cursor.lastrowid

        video_b64 = base64.b64encode(b"edited bytes").decode()
        captured = {}

        def fake_create(**kwargs):
            captured["response_format"] = kwargs["response_format"]
            return _completed_interaction(video_b64)

        with patch("app.tools.video_edit_tools.storage.read_video", return_value=b"x"), \
             patch("app.tools.video_edit_tools.storage.save_video", return_value="out.mp4"), \
             patch("app.tools.video_edit_tools._build_client") as mock_build_client:
            mock_client = MagicMock()
            mock_client.interactions.create.side_effect = fake_create
            mock_build_client.return_value = mock_client

            await video_edit_tools.edit_video_with_omni(source_id, "change the color")

        assert captured["response_format"].aspect_ratio is None
```

Run it once to confirm it fails on import (module doesn't exist yet):

```bash
pytest tests/unit/test_video_edit_tools.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.tools.video_edit_tools'` (or `ImportError`).

**Note on `test_db` fixture and `pytest.mark.asyncio`:** check `tests/conftest.py` for the exact `test_db` fixture name/behavior and whether `pytest-asyncio` is already configured (`asyncio_mode` in `pytest.ini`, or per-test `@pytest.mark.asyncio` — mirror exactly what `tests/unit/test_video_tools.py`'s existing async tests use, e.g. `test_generate_video_from_product_mock`, rather than assuming).

- [ ] **Step 2: Implement `app/tools/video_edit_tools.py`**

```python
"""Post-generation visual video editing via Gemini Omni Flash's Interactions
API (Phase 14c — experimental, opt-in, ENABLE_OMNI_EDIT-gated).

Two live-discovered API contract details, undocumented by Google, that this
module must always honor (see .docs/version2-plan/14c-omni-video-editing.md):
  1. VideoContent.data must be a pathlib.Path (or IO[bytes]) to be
     auto-base64-encoded by the SDK -- a bare str is sent as literal
     (corrupt) "base64 data" and only fails server-side with a 400.
  2. response_format must never set aspect_ratio for an edit-task call --
     the server derives it from the input video and 400s if set explicitly.

Interactions (this module) and Veo's long-running operations (video_tools.py)
are different API primitives with different polling methods
(client.interactions.get() vs client.operations.get()) -- deliberately NOT
sharing a polling helper between them (14b's own finding).
"""

import asyncio
import base64
import logging
import tempfile
import time
from pathlib import Path

from google import genai
from google.genai import interactions as im

from .. import storage
from ..config import OMNI_EDIT_MODEL
from ..database.db import get_db_cursor

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "incomplete", "budget_exceeded"}
_POLL_INTERVAL_SECONDS = 10


class OmniEditError(Exception):
    """Base error for Omni Flash edit-tool failures."""


def _load_video_bytes_for_edit(video_id: int) -> tuple[bytes, dict]:
    """Resolve a campaign_videos row to (video_bytes, row_dict).

    Reuses storage.read_video(), which already handles local-vs-GCS storage
    mode -- this function does not need its own branching for that.
    """
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM campaign_videos WHERE id = ?", (video_id,))
        row = cursor.fetchone()
    if not row:
        raise OmniEditError(f"Video {video_id} not found")
    row_dict = dict(row)
    video_bytes = storage.read_video(row_dict["video_filename"])
    return video_bytes, row_dict


def _build_client() -> genai.Client:
    return genai.Client()  # picks up GOOGLE_GENAI_USE_VERTEXAI/PROJECT/LOCATION from env


def _extract_video_bytes(interaction) -> bytes:
    """Pull the model_output step's video content and base64-decode it."""
    for step in getattr(interaction, "steps", None) or []:
        if getattr(step, "type", None) != "model_output":
            continue
        for content in getattr(step, "content", None) or []:
            if getattr(content, "type", None) == "video":
                data_b64 = getattr(content, "data", None)
                if data_b64:
                    return base64.b64decode(data_b64)
                uri = getattr(content, "uri", None)
                if uri:
                    raise OmniEditError(f"Video delivered as uri, not inline: {uri}")
    output_video = getattr(interaction, "output_video", None)
    if output_video:
        data_b64 = getattr(output_video, "data", None)
        if data_b64:
            return base64.b64decode(data_b64)
    raise OmniEditError("Omni Flash response completed but contained no video content")


async def _wait_for_omni_interaction(client, interaction, max_wait_time: int):
    """Poll a background interaction to a terminal status."""
    waited = 0
    status = getattr(interaction, "status", None)
    while status not in _TERMINAL_STATUSES:
        if waited >= max_wait_time:
            raise TimeoutError(
                f"Omni Flash edit timed out after {max_wait_time}s (last status={status})"
            )
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        waited += _POLL_INTERVAL_SECONDS
        interaction = client.interactions.get(interaction.id)
        status = getattr(interaction, "status", None)
    return interaction


async def edit_video_with_omni(
    video_id: int,
    edit_instruction: str,
    *,
    max_wait_time: int = 300,
) -> dict:
    """Apply a targeted visual edit to an existing generated video via
    Gemini Omni Flash's Interactions API (video_config.task="edit").

    Verified working for single-attribute visual edits (e.g. "change the
    shirt color to red"). NOT for audio/music/dialogue/language changes --
    Omni Flash does not support voice editing (confirmed broken; see the
    phase doc). NOT for multi-attribute instructions or chained/iterative
    revision (previous_interaction_id) -- unverified, do not rely on it.

    Args:
        video_id: DB id of a previously generated video (campaign_videos.id).
        edit_instruction: natural-language, single-attribute edit request.
        max_wait_time: seconds to wait for the background interaction to
            reach a terminal status.

    Returns:
        On success: {"success": True, "video_id": <new id>,
            "source_video_id": video_id, "video_filename": ...,
            "backend": "omni_flash", "interaction_id": ..., "duration_seconds": ...}
        On failure: {"success": False, "error": <message>,
            "error_type": "not_found" | "unsupported_edit" | "timeout" | "api_error"}
    """
    try:
        video_bytes, row = _load_video_bytes_for_edit(video_id)
    except OmniEditError as e:
        return {"success": False, "error": str(e), "error_type": "not_found"}

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = Path(tmp.name)

    try:
        client = _build_client()
        user_step = im.UserInputStep(
            content=[
                im.VideoContent(data=tmp_path, mime_type="video/mp4"),
                im.TextContent(text=edit_instruction),
            ]
        )
        generation_config = im.GenerationConfig(video_config=im.VideoConfig(task="edit"))
        response_format = im.VideoResponseFormat(type="video", delivery="inline")

        try:
            interaction = client.interactions.create(
                model=OMNI_EDIT_MODEL,
                input=[user_step],
                generation_config=generation_config,
                response_format=response_format,
                background=True,
            )
            interaction = await _wait_for_omni_interaction(client, interaction, max_wait_time)
        except TimeoutError as e:
            return {"success": False, "error": str(e), "error_type": "timeout"}
        except Exception as e:
            logger.exception("Omni Flash edit call failed for video_id=%s", video_id)
            return {"success": False, "error": str(e), "error_type": "api_error"}

        if interaction.status != "completed":
            return {
                "success": False,
                "error": f"Omni Flash interaction ended with status={interaction.status}",
                "error_type": "unsupported_edit",
            }

        try:
            edited_bytes = _extract_video_bytes(interaction)
        except OmniEditError as e:
            return {"success": False, "error": str(e), "error_type": "api_error"}
    finally:
        tmp_path.unlink(missing_ok=True)

    new_filename = f"omni-edit-{int(time.time() * 1000)}.mp4"
    storage.save_video(new_filename, edited_bytes)

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO campaign_videos
                (campaign_id, product_id, video_filename, status,
                 duration_seconds, aspect_ratio, source_video_id,
                 scene_prompt, video_prompt, pipeline_type)
            VALUES (?, ?, ?, 'generated', ?, ?, ?, ?, ?, 'omni-edit')
            """,
            (
                row["campaign_id"],
                row["product_id"],
                new_filename,
                row["duration_seconds"],
                row["aspect_ratio"],
                video_id,
                row.get("scene_prompt"),
                edit_instruction,
            ),
        )
        new_video_id = cursor.lastrowid

    logger.info(
        "omni edit: source_video_id=%s new_video_id=%s interaction_id=%s",
        video_id,
        new_video_id,
        interaction.id,
    )

    return {
        "success": True,
        "video_id": new_video_id,
        "source_video_id": video_id,
        "video_filename": new_filename,
        "backend": "omni_flash",
        "interaction_id": interaction.id,
        "duration_seconds": row["duration_seconds"],
    }


async def translate_video_dialogue(video_id: int, target_language: str) -> dict:
    """NOT IMPLEMENTED. Documented placeholder for a researched-and-rejected
    capability -- see .docs/version2-plan/14c-omni-video-editing.md's "Out of
    scope" section. Gemini Omni Flash does not support voice editing/dubbing
    on any surface; a live test produced a partial, code-switched
    translation with unsynced lip movement. Do not wire this into any agent.
    If ever implemented, it must target a different model/product, with its
    own research spike first.
    """
    raise NotImplementedError(
        "Dialogue translation/dubbing is not supported by Gemini Omni Flash "
        "(see .docs/version2-plan/14c-omni-video-editing.md). This function "
        "is a documented placeholder, not a real backend."
    )
```

- [ ] **Step 3: Run the tests, confirm all pass**

```bash
pytest tests/unit/test_video_edit_tools.py -v
```

Expected: all tests PASS, zero network calls (every `client.interactions.*` call is mocked).

- [ ] **Step 4: Run `make lint` and the full fast suite**

```bash
make lint
make test
```

Expected: lint clean; full suite green (previous count + this file's new tests).

- [ ] **Step 5: Commit**

```bash
git add app/tools/video_edit_tools.py tests/unit/test_video_edit_tools.py
git commit -m "feat(14c): add edit_video_with_omni tool + network-free unit tests"
```

---

### Task 3: Review Agent wiring, live test, demo scenario, docs

**Files:**
- Modify: `app/agent.py` (imports ~line 47 and ~100; `REVIEW_AGENT_INSTRUCTION` ~line 446; `review_agent` tools list ~line 521-539)
- Create: `tests/live/test_omni_video_edit.py`
- Modify: `docs/demo-scenarios/fashion.md` (add one scene)
- Modify: root `DEMO_GUIDE.md` ("Workstream Testing Journeys" section)

**Interfaces:**
- Consumes: `edit_video_with_omni`, `translate_video_dialogue` (Task 2); `app.config.ENABLE_OMNI_EDIT` (Task 1).

- [ ] **Step 1: Wire the tool into `app/agent.py`, gated by the flag**

Add to the config import (line 47):

```diff
-from .config import APP_DESCRIPTION, APP_NAME, DB_PATH, MODEL
+from .config import APP_DESCRIPTION, APP_NAME, DB_PATH, ENABLE_OMNI_EDIT, MODEL
```

Add a new import near the other tool imports (after the `from .tools.video_tools import (...)` block, ~line 100+):

```python
from .tools.video_edit_tools import edit_video_with_omni
```

Append a conditional instruction section right before `REVIEW_AGENT_INSTRUCTION`'s closing `"""` (~line 519, just before "## Response Guidelines" or after it — append after the whole existing string):

```python
_OMNI_EDIT_INSTRUCTION_SECTION = """

## Experimental: Visual Video Editing (Omni Flash)

**edit_video_with_omni(video_id, edit_instruction)** - Request a targeted
visual edit to an existing generated video (e.g. "change the shirt color to
red", "remove the coffee cup from the counter"). This is an EXPERIMENTAL,
opt-in capability backed by Gemini Omni Flash, separate from the standard
Veo generation pipeline:
- Only single-attribute visual edits are verified to work well; avoid
  combining multiple unrelated changes in one instruction.
- Do NOT use this for audio, dialogue, music, or language changes -- Omni
  Flash does not support voice/audio editing. If asked for something like
  that, explain plainly that it isn't supported rather than attempting the
  tool.
- The edit produces a NEW video (a new video_id) and leaves the original
  untouched; mention both ids in your response so the user can compare.
"""

if ENABLE_OMNI_EDIT:
    REVIEW_AGENT_INSTRUCTION = REVIEW_AGENT_INSTRUCTION + _OMNI_EDIT_INSTRUCTION_SECTION
```

Update the `review_agent`'s tool list (~line 521-539) from a literal list to a built list:

```diff
+_review_agent_tools = [
+    # New review table tools (PRIMARY)
+    get_video_review_table,
+    get_video_details,
+    # Legacy and activation tools
+    list_pending_videos,
+    activate_video,
+    activate_batch,
+    pause_video,
+    archive_video,
+    get_video_status,
+    get_activation_summary,
+    generate_additional_metrics,
+]
+if ENABLE_OMNI_EDIT:
+    _review_agent_tools.append(edit_video_with_omni)
+
 review_agent = LlmAgent(
     model=MODEL,
     name="review_agent",
     description="Manages HITL video activation workflow: lists pending videos, activates videos to push live (generates metrics), pauses/archives videos, checks status. Videos must be activated before metrics appear.",
     instruction=REVIEW_AGENT_INSTRUCTION,
-    tools=[
-        # New review table tools (PRIMARY)
-        get_video_review_table,
-        get_video_details,
-        # Legacy and activation tools
-        list_pending_videos,
-        activate_video,
-        activate_batch,
-        pause_video,
-        archive_video,
-        get_video_status,
-        get_activation_summary,
-        generate_additional_metrics,
-    ],
+    tools=_review_agent_tools,
 )
```

- [ ] **Step 2: Regression test — flag off leaves everything unchanged**

```python
# add to tests/unit/test_agent.py (or wherever review_agent's tool list is already tested — check first)
def test_review_agent_tools_unchanged_when_omni_edit_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_OMNI_EDIT", "false")
    import importlib
    from app import config, agent
    importlib.reload(config)
    importlib.reload(agent)
    tool_names = {t.__name__ for t in agent.review_agent.tools}
    assert "edit_video_with_omni" not in tool_names
```

Run: `pytest tests/unit/test_agent.py -k omni_edit_disabled -v` (adjust path once you've located the actual existing agent test file). Expected: PASS.

- [ ] **Step 3: Run the full fast suite + lint**

```bash
make lint
make test
```

Expected: green, byte-identical behavior confirmed for the default (flag-off) path.

- [ ] **Step 4: Commit the agent wiring**

```bash
git add app/agent.py tests/unit/test_agent.py
git commit -m "feat(14c): register edit_video_with_omni on review_agent, gated by ENABLE_OMNI_EDIT"
```

- [ ] **Step 5: Write the live-tier test**

Create `tests/live/test_omni_video_edit.py`:

```python
"""Live-tier Omni Flash edit test (Phase 14c) -- REAL calls against Vertex
AI's gemini-omni-flash-preview.

Cost: one edit-task interaction against an 8s 720p-class video (~seconds of
latency, no meaningful quota concern -- Preview tier, not billed like GA
Veo). Requires ENABLE_OMNI_EDIT-independent direct import (this test calls
the tool function directly, not through the agent, so the flag doesn't
gate it here -- the flag only gates agent registration).
"""

import pytest

from app.database.db import get_db_cursor
from app.tools.video_edit_tools import edit_video_with_omni

pytestmark = pytest.mark.live


@pytest.fixture
def seeded_video(test_db):
    """Insert one real, tiny video row pointing at a real pipeline-generated
    asset already present in this repo's demo video assets (check
    app/database/mock_data.py's REAL_VIDEOS for an existing filename to
    reuse rather than generating a fresh one for this test)."""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, product_id FROM campaigns WHERE status = 'active' LIMIT 1")
        campaign_row = cursor.fetchone()
        cursor.execute(
            "SELECT video_filename FROM campaign_videos WHERE campaign_id = ? LIMIT 1",
            (campaign_row["id"],),
        )
        video_row = cursor.fetchone()
    return video_row, campaign_row


class TestLiveOmniEdit:
    @pytest.mark.asyncio
    async def test_single_attribute_edit_succeeds(self, seeded_video):
        video_row, campaign_row = seeded_video
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT id FROM campaign_videos WHERE video_filename = ?",
                (video_row["video_filename"],),
            )
            video_id = cursor.fetchone()["id"]

        result = await edit_video_with_omni(
            video_id,
            "Edit this video: make the background slightly warmer in color "
            "tone. Keep everything else -- the product, the model, the "
            "framing -- exactly the same.",
        )

        assert result["success"] is True, result
        assert result["backend"] == "omni_flash"
        assert result["source_video_id"] == video_id
        assert result["video_id"] != video_id
```

Note: adjust the fixture to whatever's the least-friction way to get a real `video_filename` that exists on disk in this worktree's `generated/` (or GCS, per whatever storage mode this worktree runs in) — check `app/database/mock_data.py`'s `REAL_VIDEOS` dict for actual filenames, don't assume one.

- [ ] **Step 6: Run the live test for real (costs a real, small API call)**

```bash
set -a; source app/.env; set +a
GOOGLE_CLOUD_LOCATION=global .venv/bin/pytest tests/live/test_omni_video_edit.py -v
```

Expected: PASS, real edited video saved via `storage.save_video`, new `campaign_videos` row with `source_video_id` set.

- [ ] **Step 7: Commit**

```bash
git add tests/live/test_omni_video_edit.py
git commit -m "test(14c): live-tier test for edit_video_with_omni against real Vertex AI"
```

- [ ] **Step 8: Add a demo scenario scene**

Read `docs/demo-scenarios/fashion.md` in full first (this task's implementer must read the existing file before editing it — do not guess its current scene numbering). Add a new scene following its existing Act/Scene format, e.g.:

```markdown
### Scene: Experimental visual video edit (Omni Flash, ws14c)

**Setup:** `ENABLE_OMNI_EDIT=true make dev` (default is off -- this scene
only applies when explicitly enabled).

**Query:** "Show me the pending or activated videos for campaign 1, then
request an edit on the first one: change the background color tone to be
warmer."

**Expected tool calls:** `get_video_review_table` (or `get_video_details`)
followed by `edit_video_with_omni(video_id=<id>, edit_instruction=...)`.

**Expect:** the tool call succeeds, the response references both the
original `video_id` and a new `video_id` (the edited result), and the new
video is visible via `get_video_review_table()` on a subsequent turn with
`source_video_id` traceable in the DB.

**Pass criteria:** the edit tool fires with a plausible single-attribute
instruction; a new video row appears; the original video is untouched.

**Fail criteria:** the tool is invoked with `ENABLE_OMNI_EDIT` unset/false
and still appears in the agent's tool list (regression), or the edit
instruction bundles multiple unrelated changes (a case this phase never
verified working).
```

- [ ] **Step 9: Verify via `verifying-with-demo-scenarios`**

Dispatch the `demo-scenario-verifier` subagent against this new scene (per the skill: kill anything on :8501 first, launch `ENABLE_OMNI_EDIT=true make dev` in this worktree, drive the scene via chrome-devtools MCP, inspect the Trace tab for the `edit_video_with_omni` call and its arguments). Separately, re-verify one or two of the fashion suite's *existing* scenes with `ENABLE_OMNI_EDIT` unset (default) to confirm zero behavior change — this is the regression half of the check, not optional.

- [ ] **Step 10: Add the journey to `DEMO_GUIDE.md`**

Per CLAUDE.md's ws11a rule, add a "Workstream 14c" entry to root `DEMO_GUIDE.md`'s "Workstream Testing Journeys" section: the copy-paste prompt from Step 8's scene, the `ENABLE_OMNI_EDIT=true` setup note, and the expected before/after (two video ids, lineage).

- [ ] **Step 11: Record WORK_LOG checkpoint 5 (verification result)**

Append to `.docs/version2-plan/working-docs/14c-omni-video-editing/WORK_LOG.md`: pass/fail, evidence path from the verifier, and confirmation that the flag-off regression check passed.

- [ ] **Step 12: Commit the docs**

```bash
git add docs/demo-scenarios/fashion.md DEMO_GUIDE.md .docs/version2-plan/working-docs/14c-omni-video-editing/WORK_LOG.md
git commit -m "docs(14c): demo scenario + DEMO_GUIDE journey for edit_video_with_omni"
```

---

## Self-Review (performed at plan time)

- **Spec coverage:** every working-doc element maps to a task — SDK bump + config flag + lineage column (T1), tool module + network-free tests with the two live-discovered contract-detail regression tests (T2), agent wiring + flag-off regression + live test + demo verification + docs (T3). `translate_video_dialogue` placeholder covered in T2, never imported into `agent.py` (T3 doesn't touch it) per the Global Constraints.
- **Placeholder scan:** no "TBD"/"add validation later" language. The one deliberately-approximate spot is T3 Step 5's fixture comment ("adjust... check `REAL_VIDEOS`... don't assume one") — this is intentional: the implementer must read `mock_data.py` for a real filename rather than the plan guessing one that may not match this worktree's actual seeded assets.
- **Type consistency:** `edit_video_with_omni(video_id: int, edit_instruction: str, *, max_wait_time: int = 300) -> dict` is identical across T2's implementation, T2's tests, T3's agent wiring, and T3's live test. `OmniEditError` defined once in T2, used only within `video_edit_tools.py` (never imported elsewhere) — errors cross the tool boundary as dict fields (`success`, `error`, `error_type`), matching this repo's existing tool-return convention (`generate_video_from_product` et al.).
