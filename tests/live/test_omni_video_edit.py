# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Live-tier Omni Flash edit test (Phase 14c) -- REAL calls against Vertex
AI's gemini-omni-flash-preview.

Cost: one edit-task interaction against an 8s 720p-class video (~seconds of
latency, no meaningful quota concern -- Preview tier, not billed like GA
Veo). This test calls the tool function directly, not through the agent, so
ENABLE_OMNI_EDIT doesn't gate it here -- the flag only gates agent
registration (app/agent.py), not the tool itself.

DB isolation and real Vertex env come from tests/live/conftest.py's autouse
``isolated_live_db``/``live_real_environment`` fixtures (Phase 16 stage 5+) --
this file does not need its own env/DB fixtures, just a lookup against the
isolated copy of the main DB those fixtures already point ``app.config.DB_PATH``
at.

Storage: the live tier is local-first (GCS_BUCKET force-unset by
``live_real_environment``), so the source video must exist on disk under
this worktree's ``generated/`` directory. The fixture below reuses one of
the real, currently-seeded fashion assets from
``app/database/mock_data.py``'s ``REAL_VIDEOS`` dict
(``blue-floral-maxi-dress-122025-asian-beach-romantic.mp4``, campaign_videos
id 1, campaign_id 1 -- verified present in this worktree's seeded DB and its
``generated/`` directory) rather than generating a fresh video for this test.
"""

import pytest

from app.database.db import get_db_cursor
from app.tools.video_edit_tools import edit_video_with_omni

pytestmark = pytest.mark.live


@pytest.fixture
def seeded_video_id():
    """Resolve the id of a real, on-disk seeded video from the isolated live DB.

    Picks the first campaign_videos row for an active campaign whose
    video_filename actually exists in ``REAL_VIDEOS`` territory (fashion demo
    assets) -- see module docstring for why this is the least-friction real
    fixture rather than a freshly generated one.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT cv.id FROM campaign_videos cv
            JOIN campaigns c ON cv.campaign_id = c.id
            WHERE c.status = 'active'
              AND cv.video_filename = 'blue-floral-maxi-dress-122025-asian-beach-romantic.mp4'
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    assert row is not None, (
        "expected seeded video "
        "'blue-floral-maxi-dress-122025-asian-beach-romantic.mp4' "
        "(campaign_videos row) in the isolated live DB -- check "
        "app/database/mock_data.py's REAL_VIDEOS and that the matching "
        "asset exists in this worktree's generated/ directory"
    )
    return row["id"]


class TestLiveOmniEdit:
    @pytest.mark.asyncio
    async def test_single_attribute_edit_succeeds(self, seeded_video_id):
        result = await edit_video_with_omni(
            seeded_video_id,
            "Edit this video: make the background slightly warmer in color "
            "tone. Keep everything else -- the product, the model, the "
            "framing -- exactly the same.",
        )

        assert result["success"] is True, result
        assert result["backend"] == "omni_flash"
        assert result["source_video_id"] == seeded_video_id
        assert result["video_id"] != seeded_video_id

        # New row must be visible in the DB with correct lineage.
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT source_video_id, status, pipeline_type FROM campaign_videos WHERE id = ?",
                (result["video_id"],),
            )
            new_row = cursor.fetchone()
        assert new_row is not None
        assert new_row["source_video_id"] == seeded_video_id
        assert new_row["pipeline_type"] == "omni-edit"
