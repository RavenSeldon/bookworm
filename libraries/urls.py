"""
Bookworm: Little Library Finder - URL Configuration

Routes for map, API, and form submissions.
- Landing page at root '/'
- Map moved to '/map/'
- Geocoding API at '/api/geocode/'
"""

from django.urls import path
from . import views

app_name = "libraries"

urlpatterns = [
    # Landing page
    path("", views.landing_page, name="landing"),
    # Main map view
    path("map/", views.map_view, name="map"),
    # GeoJSON API
    path("api/libraries.geojson", views.libraries_geojson, name="libraries_geojson"),
    # Geocoding API
    path("api/geocode/", views.geocode_address, name="geocode"),
    # Library detail - SEO-friendly, PK-slug pattern
    path("library/<int:pk>-<slug:slug>/", views.library_detail, name="library_detail"),
    path("library/<int:pk>/", views.library_detail_bare, name="library_detail_bare"),
    # Library submission (split views)
    path('submit/', views.submit_library_form, name='submit_form'),  # GET - display form
    path('submit/create/', views.submit_library, name='submit_library'),  # POST - handle submission
    # Shelfie upload
    path(
        "library/<int:library_pk>/shelfie/", views.upload_shelfie, name="upload_shelfie"
    ),
    path(
        "library/<int:library_pk>/shelfie/form/",
        views.shelfie_form_partial,
        name="shelfie_form",
    ),
    # Issue reporting
    path("library/<int:library_pk>/report/", views.report_issue, name="report_issue"),
    path(
        "library/<int:library_pk>/report/form/",
        views.report_form_partial,
        name="report_form",
    ),
    # Shelfie photo reporting
    path(
        "shelfie/<int:shelfie_pk>/report/",
        views.report_shelfie,
        name="report_shelfie",

    ),
    path(
        "shelfie/<int:shelfie_pk>/report/form/",
        views.shelfie_report_form_partial,
        name="shelfie_report_form",
    ),
    # Steward partners + /here/ QR funnel
    path("partners/", views.partnership_form, name="partnership_form"),
    path("partners/submit/", views.partnership_submit, name="partnership_submit"),
    path("partners/thanks/", views.partnership_thanks, name="partnership_thanks"),
    path("here/", views.here_landing, name="here_landing"),
    path("here/resolve/", views.here_resolve, name="here_resolve"),
    path("here/log/", views.here_log, name="here_log"),
    # robots.txt
    path("robots.txt", views.robots_txt, name="robots_txt"),
    # Health check
    path("health/", views.health_check, name="health"),
]
