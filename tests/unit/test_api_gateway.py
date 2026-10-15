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

"""Unit tests for the UX API Gateway (`app/api_gateway.py`).

Verifies all 6 workflow steps depicted in `assets/use-case-poster.jpeg`,
configurable video generation components (subjects, settings, tone/mood,
lighting, camera, props), HITL review controls, retail media analytics,
geographic intelligence, winning formula replication, and dataset views.
"""

from __future__ import annotations

import pytest

from app.api_gateway import APIGatewayService, GatewayClient


@pytest.fixture
def client(test_db) -> GatewayClient:
    """Return a GatewayClient bound to the isolated `test_db` fixture."""
    return GatewayClient(APIGatewayService(auto_init_db=True))


class TestOverviewAndPosterWorkflow:
    """Tests for health, overview hero metrics, and the 6 poster workflow steps."""

    def test_health_endpoint(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["counts"]["campaigns"] >= 4
        assert data["counts"]["products"] >= 28
        assert data["counts"]["agents"] == 4

    def test_overview_endpoint_includes_poster_hero_and_live_kpis(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["hero_highlights"]) == 3
        assert data["value_comparison"]["old_way"]["duration"] == "4-6 weeks"
        assert data["value_comparison"]["new_way"]["duration"] == "<10 minutes"
        assert data["live_summary"]["campaigns_count"] >= 4
        assert data["live_summary"]["fashion_products_count"] == 22
        assert data["live_summary"]["retail_core_products_count"] == 6
        assert len(data["workflow_steps"]) == 6

    def test_use_cases_endpoint_maps_all_six_poster_steps(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/use-cases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_steps"] == 6
        titles = [s["title"] for s in data["steps"]]
        assert titles == [
            "Discover Your AI Team",
            "Generate Creative at Scale",
            "You Stay in Control",
            "Measure What Matters",
            "See the Big Picture",
            "Scale What Works",
        ]


class TestStep1DiscoverCampaignsAndProducts:
    """Step 1: Discover Your AI Team, campaigns, and multi-category product catalog."""

    def test_discover_endpoint(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["agents"]) == 5  # root_agent + 4 sub-agents
        assert len(data["campaigns"]) >= 4
        assert data["products_summary"]["total_count"] >= 28

    def test_agents_list_and_detail(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_specialized_agents"] == 4
        names = [a["name"] for a in data["specialized_agents"]]
        assert names == ["campaign_agent", "media_agent", "review_agent", "analytics_agent"]

        media_resp = client.get("/api/v1/agents/media_agent")
        assert media_resp.status_code == 200
        assert media_resp.json()["agent"]["display_name"] == "Media Agent"

        missing_resp = client.get("/api/v1/agents/nonexistent_agent")
        assert missing_resp.status_code == 404

    def test_products_filtering_and_onboarding(self, client: GatewayClient) -> None:
        cats_resp = client.get("/api/v1/products/categories")
        assert cats_resp.status_code == 200
        cats_data = cats_resp.json()
        assert {
            "fashion",
            "beverage",
            "electronics",
            "beauty",
            "homeware",
            "footwear",
            "grocery",
        }.issubset(set(cats_data["valid_categories"]))

        fashion_resp = client.get("/api/v1/products", params={"catalog_source": "fashion"})
        assert fashion_resp.status_code == 200
        assert fashion_resp.json()["total_count"] == 22

        retail_resp = client.get("/api/v1/products", params={"catalog_source": "retail_core"})
        assert retail_resp.status_code == 200
        assert retail_resp.json()["total_count"] == 6

        create_resp = client.post(
            "/api/v1/products",
            json={
                "name": "Aurora Sparkling Espresso",
                "category": "beverage",
                "color": "amber",
                "style": "artisan",
                "attributes": {"volume_ml": 250},
            },
        )
        assert create_resp.status_code == 201
        created_prod = create_resp.json()["product"]
        assert created_prod["name"] == "Aurora Sparkling Espresso"
        assert created_prod["presentation_mode"] == "lifestyle"

    def test_campaigns_crud(self, client: GatewayClient) -> None:
        create_resp = client.post(
            "/api/v1/campaigns",
            json={
                "product_id": 1,
                "store_name": "Miami Design District Flagship",
                "city": "Miami",
                "state": "FL",
                "category": "seasonal",
            },
        )
        assert create_resp.status_code == 201
        cid = create_resp.json()["campaign"]["id"]

        get_resp = client.get(f"/api/v1/campaigns/{cid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["campaign"]["region"] == "East Coast"

        patch_resp = client.patch(
            f"/api/v1/campaigns/{cid}",
            json={"name": "Miami Resort Showcase"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["campaign"]["name"] == "Miami Resort Showcase"


class TestStep2ConfigurableVideoComponents:
    """Step 2: Generate Creative at Scale with configurable subjects, settings, tone, lighting, camera, props."""

    def test_video_options_and_presets(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/videos/options")
        assert resp.status_code == 200
        groups = resp.json()["component_groups"]
        assert "subjects" in groups
        assert "settings" in groups
        assert "tone" in groups
        assert "visual_style" in groups
        assert "camera" in groups
        assert "production" in groups

        ethnicities = [e["value"] for e in groups["subjects"]["model_ethnicities"]]
        assert "european" in ethnicities
        assert "asian" in ethnicities
        assert "latina" in ethnicities

        settings = [s["value"] for s in groups["settings"]["settings"]]
        assert "rooftop" in settings
        assert "beach" in settings

        moods = [m["value"] for m in groups["tone"]["moods"]]
        assert "sophisticated" in moods
        assert "romantic" in moods

        presets_resp = client.get("/api/v1/videos/presets")
        assert presets_resp.status_code == 200
        assert "european_rooftop_sophisticated" in presets_resp.json()["presets"]

    def test_live_prompt_preview_reflects_custom_components(self, client: GatewayClient) -> None:
        resp = client.post(
            "/api/v1/videos/prompts/preview",
            json={
                "campaign_id": 1,
                "product_id": 1,
                "components": {
                    "presentation_mode": "model",
                    "model_ethnicity": "european",
                    "model_description": "Tall editorial model with sleek bun",
                    "setting": "rooftop",
                    "location_detail": "Manhattan skyline terrace with glass parapet",
                    "time_of_day": "sunset",
                    "weather": "sunny",
                    "mood": "sophisticated",
                    "mood_intensity": "intense",
                    "energy_level": "dynamic",
                    "lighting": "golden_backlight",
                    "visual_style": "editorial",
                    "color_grading": "warm",
                    "dominant_colors": ["gold", "cobalt"],
                    "camera_movement": "orbit",
                    "camera_angle": "low_angle",
                    "activity": "posing",
                    "props": ["sunglasses", "champagne_flute"],
                    "custom_instructions": "Emphasize silk fabric movement in the breeze",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        prompts = data["prompts"]
        assert "Manhattan skyline terrace" in prompts["stage1_image_prompt"]
        assert "Tall editorial model" in prompts["stage1_image_prompt"]
        assert "Emphasize silk fabric movement" in prompts["stage2_video_prompt"]
        assert data["variation_params"]["model_ethnicity"] == "european"
        assert data["variation_params"]["setting"] == "rooftop"
        assert data["variation_params"]["mood"] == "sophisticated"
        assert data["variation_params"]["props"] == ["sunglasses", "champagne_flute"]

    def test_generate_single_and_batch_videos_with_components(self, client: GatewayClient) -> None:
        single_resp = client.post(
            "/api/v1/videos/generate",
            json={
                "campaign_id": 1,
                "model_ethnicity": "european",
                "setting": "rooftop",
                "time_of_day": "sunset",
                "mood": "sophisticated",
                "lighting": "golden_backlight",
                "camera_movement": "dolly_in",
                "activity": "standing",
                "props": ["sunglasses"],
                "dry_run": True,
            },
        )
        assert single_resp.status_code == 200
        vid = single_resp.json()["video"]
        assert vid["status"] == "generated"
        assert vid["variation_params"]["model_ethnicity"] == "european"
        assert vid["variation_params"]["setting"] == "rooftop"
        assert vid["variation_params"]["mood"] == "sophisticated"

        batch_resp = client.post(
            "/api/v1/videos/generate/batch",
            json={
                "campaign_id": 2,
                "model_ethnicities": ["asian", "latina"],
                "settings": ["beach", "urban"],
                "moods": ["romantic"],
                "max_variations": 4,
                "dry_run": True,
            },
        )
        assert batch_resp.status_code == 200
        batch_data = batch_resp.json()
        assert batch_data["generated_count"] == 4
        assert len(batch_data["video_ids"]) == 4


class TestStep3HITLReviewAndLifecycle:
    """Step 3: You Stay in Control (Review Agent — pending queue, batch activation, pause, archive)."""

    def test_hitl_review_and_batch_activation(self, client: GatewayClient) -> None:
        # Generate two pending videos so we can batch-activate them
        v1 = client.post(
            "/api/v1/videos/generate",
            json={"campaign_id": 1, "preset_name": "european_rooftop_sophisticated", "dry_run": True},
        ).json()["video"]["video_id"]
        v2 = client.post(
            "/api/v1/videos/generate",
            json={"campaign_id": 2, "preset_name": "latina_urban_confident", "dry_run": True},
        ).json()["video"]["video_id"]

        pending_resp = client.get("/api/v1/review/pending")
        assert pending_resp.status_code == 200
        pending_ids = [v["id"] for v in pending_resp.json().get("pending_videos", [])]
        assert v1 in pending_ids
        assert v2 in pending_ids

        # Batch activate both videos ("Activate videos X and Y")
        batch_act_resp = client.post(
            "/api/v1/videos/activate-batch",
            json={"video_ids": [v1, v2], "days_of_metrics": 14},
        )
        assert batch_act_resp.status_code == 200
        act_data = batch_act_resp.json()
        assert act_data["activated_count"] == 2

        # Verify status transitioned to 'activated' and metrics exist
        status_resp = client.get(f"/api/v1/videos/{v1}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["video_status"] == "activated"

        # Extend metrics
        ext_resp = client.post(
            f"/api/v1/videos/{v1}/extend-metrics",
            json={"additional_days": 5},
        )
        assert ext_resp.status_code == 200

        # Pause and Archive lifecycle
        pause_resp = client.post(f"/api/v1/videos/{v1}/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["new_status"] == "paused"

        arch_resp = client.post(f"/api/v1/videos/{v1}/archive")
        assert arch_resp.status_code == 200
        assert arch_resp.json()["new_status"] == "archived"

        # Omni edit dry-run
        edit_resp = client.post(
            f"/api/v1/videos/{v2}/edit",
            json={"edit_instruction": "Add warm golden sunset glow", "dry_run": True},
        )
        assert edit_resp.status_code == 200
        assert edit_resp.json()["status"] == "success"


class TestStep4And5AnalyticsAndGeographicIntelligence:
    """Step 4 (Measure What Matters) & Step 5 (See the Big Picture)."""

    def test_analytics_overview_and_top_rpi_videos(self, client: GatewayClient) -> None:
        overview_resp = client.get("/api/v1/analytics/overview")
        assert overview_resp.status_code == 200
        ov = overview_resp.json()
        assert ov["primary_kpi"] == "rpi"
        assert "rpi" in ov["metric_definitions"]
        assert "dwell_time_seconds" in ov["metric_definitions"]

        top_resp = client.get("/api/v1/analytics/top-ads", params={"metric": "rpi", "limit": 5})
        assert top_resp.status_code == 200
        top_data = top_resp.json()
        assert top_data["ranked_by"] == "rpi"
        assert len(top_data["top_campaign_videos"]) >= 1

        metrics_resp = client.get("/api/v1/analytics/campaigns/1/metrics")
        assert metrics_resp.status_code == 200
        assert metrics_resp.json()["status"] == "success"

        insights_resp = client.get("/api/v1/analytics/campaigns/1/insights")
        assert insights_resp.status_code == 200
        assert insights_resp.json()["status"] == "success"

        creatives_resp = client.get("/api/v1/analytics/campaigns/1/creatives")
        assert creatives_resp.status_code == 200
        assert creatives_resp.json()["status"] == "success"

    def test_geographic_maps_and_west_vs_east_coast_comparison(self, client: GatewayClient) -> None:
        maps_resp = client.get("/api/v1/maps/campaigns")
        assert maps_resp.status_code == 200
        assert maps_resp.json()["status"] == "success"

        reg_resp = client.get("/api/v1/maps/regions")
        assert reg_resp.status_code == 200
        reg_data = reg_resp.json()
        assert reg_data["status"] == "success"
        assert "West Coast" in reg_data["regions"]
        assert "East Coast" in reg_data["regions"]
        assert "west_coast_vs_east_coast" in reg_data
        assert reg_data["top_region_by_rpi"] is not None

        demo_resp = client.get("/api/v1/maps/demographics", params={"city": "Los Angeles", "state": "CA"})
        assert demo_resp.status_code == 200


class TestStep6WinningFormulaAndChatRouter:
    """Step 6: Scale What Works (Winning Formula) and Natural-Language Poster Prompts."""

    def test_extract_and_apply_winning_formula(self, client: GatewayClient) -> None:
        wf_resp = client.get("/api/v1/optimization/winning-formula")
        assert wf_resp.status_code == 200
        wf_data = wf_resp.json()
        assert wf_data["status"] == "success"
        assert "winning_formula" in wf_data
        assert len(wf_data["dna_summary"]) >= 4

        source_vid_id = wf_data["winning_formula"]["source_video_id"]
        apply_resp = client.post(
            "/api/v1/optimization/apply-winning-formula",
            json={
                "source_video_id": source_vid_id,
                "target_campaign_id": 3,
                "dry_run": True,
            },
        )
        assert apply_resp.status_code == 200
        applied = apply_resp.json()
        assert applied["status"] == "success"
        assert applied["target_campaign"]["id"] == 3
        assert applied["new_video"]["campaign_id"] == 3
        assert applied["new_video"]["status"] == "generated"

    def test_all_six_poster_sample_prompts_via_chat_endpoint(self, client: GatewayClient) -> None:
        # Ensure videos 5 and 7 exist so "Activate videos 5 and 7" & "from video 5 to campaign 3" work
        while len(client.get("/api/v1/videos").json()["videos"]) < 7:
            client.post(
                "/api/v1/videos/generate",
                json={
                    "campaign_id": 1,
                    "model_ethnicity": "european",
                    "setting": "rooftop",
                    "time_of_day": "sunset",
                    "mood": "sophisticated",
                    "dry_run": True,
                },
            )

        poster_prompts = [
            ("What agents are available and what are our current campaigns?", "root_agent"),
            ("Generate a video with a European model on a rooftop at sunset, sophisticated mood", "media_agent"),
            ("Activate videos 5 and 7", "review_agent"),
            ("Which videos have the highest RPI?", "analytics_agent"),
            ("Compare West Coast vs East Coast performance", "analytics_agent"),
            ("Apply the winning formula from video 5 to campaign 3", "media_agent"),
        ]

        for prompt_text, expected_agent in poster_prompts:
            resp = client.post("/api/v1/agents/chat", json={"prompt": prompt_text, "dry_run_media": True})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "success"
            assert payload["routed_agent"] == expected_agent
            assert len(payload["reply"]) > 10


class TestDatasetsExplorer:
    """Tests for viewing, filtering, and managing all 12 datasets."""

    def test_list_and_browse_all_datasets(self, client: GatewayClient) -> None:
        list_resp = client.get("/api/v1/datasets")
        assert list_resp.status_code == 200
        ds_list = list_resp.json()
        assert ds_list["total_datasets"] == 12
        names = [d["name"] for d in ds_list["datasets"]]
        expected = [
            "fashion_catalog",
            "retail_core_catalog",
            "products",
            "campaigns",
            "videos",
            "video_metrics",
            "video_attribution",
            "ad_plays",
            "audience_visits",
            "demo_meta",
            "legacy_ads",
            "assets",
        ]
        assert names == expected

        for ds_name in expected:
            resp = client.get(f"/api/v1/datasets/{ds_name}", params={"limit": 5})
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "success"
            assert body["dataset"] == ds_name
            assert isinstance(body["records"], list)

    def test_dataset_filtering_and_unknown_dataset(self, client: GatewayClient) -> None:
        fashion_ds = client.get("/api/v1/datasets/fashion_catalog", params={"q": "floral"})
        assert fashion_ds.status_code == 200
        assert fashion_ds.json()["total_count"] >= 1

        unknown = client.get("/api/v1/datasets/not_a_real_dataset")
        assert unknown.status_code == 404


class TestUXDesignerObjects:
    """Tests verifying complete support for UX Designer objects defined in `object.js`."""

    def test_ux_enums_match_object_js_specification(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/ux/enums")
        assert resp.status_code == 200
        data = resp.json()

        # Status enum values from object.js
        expected_status = {
            "NONE": 0,
            "GENERATING_ACTIVE": 1,
            "GENERATING_COMPLETE": 2,
            "GENERATING_FAILED": 3,
            "REVIEW_NEEDED": 4,
            "APPROVAL_UPDATED": 5,
            "TESTING_ACTIVE": 6,
            "TESTING_COMPLETE": 7,
            "TESTING_FAILED": 8,
        }
        assert data["Status"] == expected_status

        # ApprovalStatus enum values from object.js
        expected_approval = {
            "NONE": 0,
            "APPROVED": 1,
            "REJECTED": 2,
        }
        assert data["ApprovalStatus"] == expected_approval

    def test_ux_schema_endpoint(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/ux/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "enums" in data
        assert "campaign_schema" in data
        assert "video_schema" in data

    def test_ux_campaigns_list_and_detail_conforms_to_campaign_example(
        self, client: GatewayClient
    ) -> None:
        resp = client.get("/api/v1/ux/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_count"] >= 4
        assert len(data["campaigns"]) >= 4

        camp = data["campaigns"][0]
        # Verify all fields from campaignExample in object.js
        assert isinstance(camp["id"], str)
        assert len(camp["id"]) >= 6  # 6-digit formatted id e.g. "000001"
        assert isinstance(camp["name"], str)
        assert isinstance(camp["owner"], str)
        assert isinstance(camp["shared_with"], list)
        assert isinstance(camp["created_date"], str)
        assert isinstance(camp["modified_date"], str)
        assert isinstance(camp["is_template"], bool)
        assert isinstance(camp["is_favorite"], bool)
        assert isinstance(camp["is_archived"], bool)
        assert isinstance(camp["status"], int)
        assert isinstance(camp["status_meta"], dict)
        assert "quantity" in camp["status_meta"]
        assert "end_date" in camp["status_meta"]
        assert isinstance(camp["thumbnail"], str)
        assert isinstance(camp["description"], str)

        # Settings block
        settings = camp["settings"]
        for section in ("overall", "items", "people", "performance", "setting", "audio"):
            assert section in settings
            assert "prompt" in settings[section]
            assert "files" in settings[section]
            assert isinstance(settings[section]["files"], list)

        assert isinstance(settings["languages"], list)
        assert "en-US" in settings["languages"]
        assert isinstance(settings["guidelines"], list)
        assert settings["format"]["duration"] == 8
        assert isinstance(settings["format"]["aspect_ratios"], list)
        assert settings["format"]["resolution"] == "1080p"
        assert settings["testing"]["variants_per_generation"] == 10
        assert settings["testing"]["duration"] == 24

        # Videos collection
        assert isinstance(camp["videos"], list)

        # Test single campaign get
        single_resp = client.get(f"/api/v1/ux/campaigns/{int(camp['id'])}")
        assert single_resp.status_code == 200
        single_camp = single_resp.json()
        assert single_camp["id"] == camp["id"]
        assert len(single_camp["videos"]) >= 1

    def test_ux_videos_conform_to_video_example(self, client: GatewayClient) -> None:
        resp = client.get("/api/v1/ux/videos")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_count"] >= 4

        video = data["videos"][0]
        # Verify all fields from videoExample in object.js
        assert isinstance(video["id"], str)
        assert len(video["id"]) >= 6  # 6-digit formatted id e.g. "000001"
        assert isinstance(video["name"], str)
        assert isinstance(video["parent_id"], str)
        assert isinstance(video["campaign_id"], str)
        assert isinstance(video["created_date"], str)
        assert isinstance(video["is_favorite"], bool)
        assert isinstance(video["is_archived"], bool)
        assert isinstance(video["approval_status"], int)
        assert video["approval_status"] in (0, 1, 2)
        assert isinstance(video["status"], int)
        assert isinstance(video["status_meta"], dict)
        assert "quantity" in video["status_meta"]
        assert "end_date" in video["status_meta"]
        assert isinstance(video["thumbnail"], str)
        assert isinstance(video["description"], str)
        assert isinstance(video["url"], str)
        assert isinstance(video["testing_period"], dict)
        assert "start_date" in video["testing_period"]
        assert "end_date" in video["testing_period"]
        assert isinstance(video["duration"], int)
        assert isinstance(video["impressions"], int)
        assert isinstance(video["impressions_id"], str)
        assert isinstance(video["revenue"], (int, float))
        assert isinstance(video["revenue_id"], str)
        assert isinstance(video["rank"], int)
        assert isinstance(video["settings"], dict)

        # Test single video get
        single_resp = client.get(f"/api/v1/ux/videos/{int(video['id'])}")
        assert single_resp.status_code == 200
        single_vid = single_resp.json()
        assert single_vid["id"] == video["id"]

    def test_format_ux_query_parameter_on_standard_endpoints(
        self, client: GatewayClient
    ) -> None:
        # Standard campaigns with format=ux
        camps_resp = client.get("/api/v1/campaigns", params={"format": "ux"})
        assert camps_resp.status_code == 200
        camps_data = camps_resp.json()
        assert camps_data["status"] == "success"
        assert isinstance(camps_data["campaigns"][0]["id"], str)
        assert "settings" in camps_data["campaigns"][0]

        # Standard single campaign with format=ux
        single_camp_resp = client.get("/api/v1/campaigns/1", params={"format": "ux"})
        assert single_camp_resp.status_code == 200
        assert single_camp_resp.json()["id"] == "000001"
        assert "videos" in single_camp_resp.json()

        # Standard videos with format=ux
        vids_resp = client.get("/api/v1/videos", params={"format": "ux"})
        assert vids_resp.status_code == 200
        vids_data = vids_resp.json()
        assert vids_data["status"] == "success"
        assert isinstance(vids_data["videos"][0]["id"], str)
        assert "testing_period" in vids_data["videos"][0]

        # Standard single video with format=ux
        single_vid_resp = client.get("/api/v1/videos/1", params={"format": "ux"})
        assert single_vid_resp.status_code == 200
        assert single_vid_resp.json()["id"] == "000001"

    def test_ux_campaign_create_and_update(self, client: GatewayClient) -> None:
        create_payload = {
            "name": "Summer Running Glasses Campaign",
            "product_id": 1,
            "store_name": "Santa Monica Pier",
            "city": "Santa Monica",
            "state": "CA",
            "description": "High performance eyewear ad campaign",
        }
        resp = client.post("/api/v1/ux/campaigns", body=create_payload)
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Summer Running Glasses Campaign"
        assert isinstance(created["id"], str)
        assert "settings" in created

        new_cid = int(created["id"])
        # Update campaign
        update_resp = client.patch(
            f"/api/v1/ux/campaigns/{new_cid}",
            body={"name": "Updated Running Glasses Campaign", "status": 5},
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["name"] == "Updated Running Glasses Campaign"
        assert updated["status"] == 5

    def test_ux_video_approval_workflow(self, client: GatewayClient) -> None:
        # Check initial approval status of video 1
        v1_resp = client.get("/api/v1/ux/videos/1")
        assert v1_resp.status_code == 200

        # Set approval status to APPROVED (1)
        app_resp = client.post("/api/v1/ux/videos/1/approval", body={"approval_status": 1})
        assert app_resp.status_code == 200
        approved = app_resp.json()
        assert approved["approval_status"] == 1
        assert approved["status"] == 6  # TESTING_ACTIVE

        # Set approval status to REJECTED (2) -> archived
        rej_resp = client.post("/api/v1/ux/videos/1/approval", body={"approval_status": 2})
        assert rej_resp.status_code == 200
        rejected = rej_resp.json()
        assert rejected["approval_status"] == 2
        assert rejected["is_archived"] is True
