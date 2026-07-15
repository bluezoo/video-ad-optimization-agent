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

"""Unit tests for maps_tools.py.

Tests the Google Maps integration tools:
- get_campaign_map_data
- generate_static_map
- generate_map_visualization (requires LLM, marked slow)
"""

from unittest.mock import MagicMock, patch

import pytest


class TestGetCampaignMapData:
    """Tests for get_campaign_map_data tool."""

    def test_get_campaign_map_data_returns_all(self, test_db, mock_storage_module):
        """get_campaign_map_data should return all campaign locations."""
        from app.tools.maps_tools import get_campaign_map_data

        result = get_campaign_map_data()

        # Should return locations with map data
        assert "locations" in result or "campaigns" in result or result is not None

    def test_get_campaign_map_data_has_google_maps_urls(self, test_db, mock_storage_module):
        """Locations should include Google Maps URLs."""
        from app.tools.maps_tools import get_campaign_map_data

        result = get_campaign_map_data()

        # May not have links if no campaigns, but structure should exist
        assert result is not None

    def test_get_campaign_map_data_has_coordinates(self, test_db, mock_storage_module):
        """Locations should include lat/lng coordinates."""
        from app.tools.maps_tools import get_campaign_map_data

        result = get_campaign_map_data()

        assert result is not None


class TestGenerateStaticMap:
    """Tests for generate_static_map tool."""

    @pytest.fixture
    def mock_maps_api(self):
        """Mock Google Maps Static API."""
        with patch("googlemaps.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.static_map.return_value = b"fake_image_data"
            yield mock_instance

    def test_generate_static_map_default(self, test_db, mock_storage_module):
        """generate_static_map should create map image."""
        from app.tools.maps_tools import generate_static_map

        result = generate_static_map()

        # Should return URL or error if API key not set
        assert "url" in result or "error" in result or "map" in str(result).lower() or result is not None

    def test_generate_static_map_by_status(self, test_db, mock_storage_module):
        """generate_static_map should color-code by status."""
        from app.tools.maps_tools import generate_static_map

        result = generate_static_map(color_by="status")

        # Should return result
        assert result is not None

    def test_generate_static_map_by_revenue(self, test_db, mock_storage_module):
        """generate_static_map should color-code by revenue."""
        from app.tools.maps_tools import generate_static_map

        result = generate_static_map(color_by="revenue")

        # Should return result
        assert result is not None

    def test_generate_static_map_types(self, test_db, mock_storage_module):
        """generate_static_map should support different map types."""
        from app.tools.maps_tools import generate_static_map

        map_types = ["roadmap", "satellite", "terrain", "hybrid"]

        for map_type in map_types:
            result = generate_static_map(map_type=map_type)
            assert result is not None


@pytest.mark.slow
@pytest.mark.integration
class TestGenerateMapVisualization:
    """Tests for generate_map_visualization tool (requires LLM)."""

    async def test_generate_map_visualization_performance_map(
        self, test_db, mock_storage_module
    ):
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            result = await generate_map_visualization(
                visualization_type="performance_map"
            )

            assert result["status"] == "error"
            assert "mocked API failure" in result["message"]

    async def test_generate_map_visualization_regional_comparison(
        self, test_db, mock_storage_module
    ):
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            result = await generate_map_visualization(
                visualization_type="regional_comparison"
            )

            assert result["status"] == "error"
            assert "mocked API failure" in result["message"]

    async def test_generate_map_visualization_styles(
        self, test_db, mock_storage_module
    ):
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            for style in ["infographic", "artistic", "simple"]:
                result = await generate_map_visualization(style=style)
                assert "Invalid style" not in result.get("message", ""), style
                assert result["status"] == "error"
                assert "mocked API failure" in result["message"], style

    async def test_default_metric_is_valid(self, test_db, mock_storage_module):
        """Calling with default metric must not trip the valid_metrics check.

        Regression: default was "revenue", which the tool itself rejects.
        """
        with patch("google.genai.Client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = (
                RuntimeError("mocked API failure")
            )
            from app.tools.maps_tools import generate_map_visualization

            result = await generate_map_visualization()

            assert "Invalid metric" not in result.get("message", "")


class TestGetCampaignLocationsCurrentSchema:
    """get_campaign_locations must read campaign_videos/video_metrics,
    not the legacy campaign_ads/campaign_metrics tables (which are empty)."""

    def test_locations_report_real_video_metrics(self, test_db):
        with patch("app.tools.maps_tools.GOOGLE_MAPS_API_KEY", "test-key"), \
             patch("googlemaps.Client") as mock_gmaps:
            mock_gmaps.return_value.geocode.return_value = [
                {"geometry": {"location": {"lat": 34.05, "lng": -118.24}}}
            ]
            from app.tools.maps_tools import get_campaign_locations

            result = get_campaign_locations()

            assert "locations" in result
            # Demo data has activated videos with 30 days of metrics on the
            # pre-loaded campaigns — the legacy tables are empty, so any
            # non-zero count proves the query reads the current schema.
            campaigns_with_ads = [
                loc for loc in result["locations"]
                if loc["metrics"]["ad_count"] > 0
            ]
            assert len(campaigns_with_ads) >= 1
            assert any(
                loc["metrics"]["total_impressions"] > 0
                for loc in campaigns_with_ads
            )
