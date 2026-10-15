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

"""tests/live conftest — live media tier (Phase 16 stage 5+).

Re-registers Task 4's live-tier fixtures for this directory via EXPLICIT
imports (no star-import). The imported functions are already decorated with
``@pytest.fixture(autouse=True)`` in tests/integration/conftest.py, so
binding their names in this conftest registers them autouse for every test
under tests/live — real Vertex env from app/.env per test (GCS_BUCKET
force-unset: live tier is local-first, open item 2) plus an isolated DB copy.

Also provides the session-scoped ``generated_media`` registry: the pipeline
tests (Task 12) and the from-scratch onboarding test (Task 13) record every
generated artifact here so the Gemini judge tests (Task 14) reuse the media
instead of regenerating it.
"""

from pathlib import Path

import pytest

from tests.integration.conftest import (  # noqa: F401
    isolated_live_db,
    live_real_environment,
)


@pytest.fixture(scope="session")
def generated_media() -> dict[str, dict]:
    """Session-wide registry of media produced by the live pipeline tests.

    Keyed by a stable label (e.g. ``wearable_video``); each entry is a dict:
    ``{"kind": "video"|"image", "path": str, "archetype": str,
    "request_context": str}`` — exactly what the Task 14 judge needs.
    """
    return {}


@pytest.fixture(scope="session")
def persisted_media_dir(tmp_path_factory) -> Path:
    """Session-persistent directory for media that must outlive per-test teardown.

    [I1, ws16 final review] Some live tests (e.g. from-scratch onboarding) run
    inside a per-test temp sandbox (``empty_live_db``'s ``PRODUCT_IMAGES_DIR``
    override) that is ``rmtree``'d at that test's own teardown. A path inside
    that sandbox dangles the moment the generating test finishes, so it must
    NOT be what gets registered in ``generated_media`` for the Task 14 judge
    to consume later in the same session — the judge tests run afterward and
    would either FileNotFoundError (ordered explicitly) or silently see
    nothing (natural collection order).

    A ``tmp_path_factory`` SESSION directory survives for the whole test
    session (pytest's own tmp-dir rotation cleans it up eventually) and is
    never the repo's real ``product-images/``/``generated/`` — nothing here
    pollutes tracked or persistent local state. Generators that need their
    output to survive their own fixture teardown should copy the artifact
    here before registering its path in ``generated_media``.
    """
    return tmp_path_factory.mktemp("persisted_media")
