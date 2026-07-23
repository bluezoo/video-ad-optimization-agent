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

"""Live from-scratch onboarding case (Phase 16 Task 13, stage 5b, open item 3).

Open item 3 asked whether a brand-new, non-seeded catalog (DEMO_DATASET=none
/ from-scratch onboarding) actually works end to end against REAL models,
and whether onboarding-generated media gets judged like any other pipeline
output. This test answers both: on a schema-only DB (no seeded products or
campaigns) it runs create_product -> generate_product_image (real image
model) -> create_campaign for a deliberately NON-fashion product (artisan
coffee beans), then registers the generated reference image in the
session-scoped ``generated_media`` registry so Task 14's judge reviews it
exactly like the Task 12 pipeline media.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

import app.config as config
from app.database.db import get_db_cursor, init_database
from app.tools.campaign_tools import create_campaign
from app.tools.onboarding_tools import create_product, generate_product_image

pytestmark = [pytest.mark.live]


@pytest.fixture
def empty_live_db(isolated_live_db, monkeypatch):
    """From-scratch DB state: schema only, no seeded products/campaigns.

    ``isolated_live_db`` (autouse, tests/integration/conftest.py) already
    repoints ``app.config.DB_PATH`` at a COPY of the seeded main DB. This
    fixture further repoints it at a fresh, schema-only temp file —
    replicating the ``empty_test_db`` fixture pattern (root conftest:180-198)
    inline here since that fixture patches ``app.config.DB_PATH`` via
    ``unittest.mock.patch`` directly, while the live tier's fixtures use
    ``monkeypatch`` on the already-imported ``config`` module object.

    Also isolates the asset directories (``product-images/``, ``generated/``)
    to a temp sandbox. The live tier writes to the persistent repo
    ``product-images/``, so a reference image left behind by a prior run would
    make ``create_product`` report ``image_status='available'`` instead of
    ``'pending'`` — breaking the from-scratch precondition on every rerun
    (ws16 DISCOVERY, 2026-07-23: create_product derives status from
    ``storage.product_image_exists`` at call time). Isolating the dirs makes
    this test hermetic and deterministic across reruns; the temp
    ``product-images`` subdir keeps that exact basename so the test's
    directory-name assertion still holds.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="test_live_empty_")
    os.close(fd)
    monkeypatch.setattr(config, "DB_PATH", db_path)

    assets_root = tempfile.mkdtemp(prefix="test_live_assets_")
    product_images = os.path.join(assets_root, "product-images")
    generated = os.path.join(assets_root, "generated")
    os.makedirs(product_images)
    os.makedirs(generated)
    monkeypatch.setattr(config, "PRODUCT_IMAGES_DIR", product_images)
    monkeypatch.setattr(config, "GENERATED_DIR", generated)

    init_database()
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass
    shutil.rmtree(assets_root, ignore_errors=True)


class TestFromScratchOnboarding:
    async def test_create_product_generate_image_attach_campaign(
        self, empty_live_db, generated_media
    ):
        """Non-fashion product, empty catalog: create -> generate image -> attach."""
        # Step 1: create a brand-new, non-fashion product on an empty catalog.
        create_result = create_product(
            name="Artisan Coffee Beans",
            category="beverage",
            description="Small-batch, single-origin artisan roasted coffee beans, 340g bag.",
            attributes={"roast": "medium", "weight_g": 340, "origin": "Ethiopia"},
        )
        assert create_result["status"] == "success", f"create_product failed: {create_result}"
        assert "storage.googleapis.com" not in json.dumps(create_result)
        product = create_result["product"]
        assert product["image_status"] == "pending"

        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = ?", (product["id"],))
            product_row = cursor.fetchone()
        assert product_row is not None
        assert product_row["name"] == "Artisan Coffee Beans"

        # Step 2: generate a reference image via the REAL image model.
        image_result = await generate_product_image(product_id=product["id"])
        assert image_result["status"] == "success", f"image generation failed: {image_result}"
        assert "storage.googleapis.com" not in json.dumps(image_result)
        assert image_result["product"]["image_status"] == "available"

        image_filename = product["image_filename"]
        image_path = os.path.join(config.PRODUCT_IMAGES_DIR, image_filename)
        assert Path(config.PRODUCT_IMAGES_DIR).name == "product-images"
        assert os.path.exists(image_path), f"image not stored locally at {image_path}"
        assert os.path.getsize(image_path) > 0

        # Step 3: attach the product to a new campaign.
        campaign_result = create_campaign(
            product_id=product["id"],
            store_name="Foothill Roasters Cafe",
            city="Portland",
            state="Oregon",
        )
        assert campaign_result["status"] == "success", f"create_campaign failed: {campaign_result}"
        assert "storage.googleapis.com" not in json.dumps(campaign_result)

        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_result["campaign"]["id"],)
            )
            campaign_row = cursor.fetchone()
        assert campaign_row is not None
        assert campaign_row["product_id"] == product["id"]

        # Register for Task 14's judge — open item 3: onboarding-generated
        # media is judged like any other pipeline output, not exempted.
        generated_media["onboarding_product_image"] = {
            "kind": "image",
            "path": image_path,
            "archetype": "onboarding-product-reference",
            "request_context": (
                "Catalog reference photo generated during from-scratch "
                "onboarding of a non-fashion product (Artisan Coffee Beans, "
                "a 340g bag of medium-roast Ethiopian coffee): clean neutral "
                "studio background, soft even lighting, product centered and "
                "fully visible, no people, no text overlays."
            ),
        }
