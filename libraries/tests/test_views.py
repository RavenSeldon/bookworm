"""
Tests for Bookworm views.

Covers: page loads, GeoJSON API, library detail (slug routing,
HTMX vs browser, 404s), form partials, health check.
"""

import json
import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


# =============================================================================
# Page Loads
# =============================================================================

class TestPageLoads:
    def test_landing_page(self, client, db):
        """Landing page returns 200 with stats."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"Bookworm" in response.content

    def test_map_page(self, client, db):
        """Map page returns 200 with Leaflet setup."""
        response = client.get("/map/")
        assert response.status_code == 200
        assert b"leaflet" in response.content.lower()

    def test_health_check(self, client, db):
        """Health check returns JSON ok."""
        response = client.get("/health/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "ok"


# =============================================================================
# GeoJSON API
# =============================================================================

class TestGeoJsonApi:
    def test_returns_feature_collection(self, client, verified_library):
        """GeoJSON endpoint returns valid FeatureCollection."""
        response = client.get("/api/libraries.geojson")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

    def test_feature_has_required_properties(self, client, verified_library):
        """Each feature has id, name, freshness, coordinates."""
        response = client.get("/api/libraries.geojson")
        data = json.loads(response.content)
        props = data["features"][0]["properties"]
        assert props["id"] == verified_library.pk
        assert props["name"] == "Oak Street Book Box"
        assert props["freshness"] in ("fresh", "stale", "needs_visit")
        coords = data["features"][0]["geometry"]["coordinates"]
        assert len(coords) == 2

    def test_bbox_filters_results(self, client, verified_library):
        """Libraries outside bbox are excluded."""
        # Vancouver library is at -123.12, 49.28
        # Use a bbox in Tokyo — should return empty
        response = client.get("/api/libraries.geojson?bbox=139.5,35.5,140.0,36.0")
        data = json.loads(response.content)
        assert len(data["features"]) == 0

    def test_bbox_includes_results(self, client, verified_library):
        """Libraries inside bbox are included."""
        # Bbox covering Vancouver
        response = client.get("/api/libraries.geojson?bbox=-124.0,49.0,-122.0,50.0")
        data = json.loads(response.content)
        assert len(data["features"]) == 1

    def test_invalid_bbox_handled_gracefully(self, client, verified_library):
        """Invalid bbox doesn't crash — returns unfiltered results."""
        response = client.get("/api/libraries.geojson?bbox=not,valid,data,here")
        assert response.status_code == 200

    def test_excludes_unverified_libraries(self, client, unverified_library):
        """Unverified libraries don't appear in GeoJSON."""
        response = client.get("/api/libraries.geojson")
        data = json.loads(response.content)
        assert len(data["features"]) == 0

    def test_excludes_inactive_libraries(self, client, inactive_library):
        """Inactive (soft-deleted) libraries don't appear."""
        response = client.get("/api/libraries.geojson")
        data = json.loads(response.content)
        assert len(data["features"]) == 0

    def test_includes_shelfie_data(self, client, verified_library, shelfie):
        """Latest shelfie data is included in feature properties."""
        response = client.get("/api/libraries.geojson")
        data = json.loads(response.content)
        props = data["features"][0]["properties"]
        assert props["shelfie_count"] == 1
        assert props["latest_shelfie"] is not None


# =============================================================================
# Library Detail
# =============================================================================

class TestLibraryDetail:
    def test_detail_with_slug(self, client, verified_library):
        """Named library accessible at /library/<pk>-<slug>/."""
        url = verified_library.get_absolute_url()
        response = client.get(url)
        assert response.status_code == 200

    def test_detail_htmx_returns_partial(self, client, verified_library):
        """HTMX request returns the partial template."""
        url = verified_library.get_absolute_url()
        response = client.get(url, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        # Partial doesn't have full HTML doc structure
        assert b"<!DOCTYPE" not in response.content
        assert b"library-detail" in response.content

    def test_detail_browser_returns_full_page(self, client, verified_library):
        """Non-HTMX request returns full HTML page."""
        url = verified_library.get_absolute_url()
        response = client.get(url)
        assert response.status_code == 200
        assert b"<!DOCTYPE" in response.content or b"<!doctype" in response.content

    def test_bare_pk_redirects_to_slug(self, client, verified_library):
        """/library/<pk>/ redirects to /library/<pk>-<slug>/ for named libraries."""
        response = client.get(f"/library/{verified_library.pk}/")
        assert response.status_code in (301, 302)
        assert verified_library.slug in response.url

    def test_bare_pk_serves_unnamed(self, client, unnamed_library):
        """/library/<pk>/ serves directly for unnamed libraries."""
        response = client.get(f"/library/{unnamed_library.pk}/")
        assert response.status_code == 200

    def test_unverified_library_returns_404(self, client, unverified_library):
        """Unverified libraries are not publicly accessible."""
        response = client.get(f"/library/{unverified_library.pk}/")
        assert response.status_code == 404

    def test_inactive_library_returns_404(self, client, inactive_library):
        """Soft-deleted libraries return 404."""
        response = client.get(f"/library/{inactive_library.pk}/")
        assert response.status_code == 404

    def test_nonexistent_library_returns_404(self, client, db):
        """Non-existent PK returns 404."""
        response = client.get("/library/99999/")
        assert response.status_code == 404


# =============================================================================
# Form Partials
# =============================================================================

class TestFormPartials:
    def test_shelfie_form_partial(self, client, verified_library):
        """Shelfie form partial loads for verified library."""
        url = f"/library/{verified_library.pk}/shelfie/form/"
        response = client.get(url)
        assert response.status_code == 200
        assert b"shelfie" in response.content.lower()

    def test_report_form_partial(self, client, verified_library):
        """Report form partial loads for verified library."""
        url = f"/library/{verified_library.pk}/report/form/"
        response = client.get(url)
        assert response.status_code == 200
        assert b"report" in response.content.lower()

    def test_submit_form_partial_htmx(self, client, db):
        """Submit form partial loads via HTMX."""
        response = client.get("/submit/", HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert b"location" in response.content.lower()