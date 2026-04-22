"""
URL configuration for SoroScan project.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from soroscan.graphql_views import ThrottledGraphQLView
from soroscan.ingest.views import audit_trail_view, contract_status, rate_limit_analytics_view
from soroscan.ingest.schema import schema

urlpatterns = [
    # Prometheus metrics — must be unauthenticated; placed before any auth middleware
    # that would intercept requests.  django_prometheus.urls exposes GET /metrics.
    path("", include("django_prometheus.urls")),

    path("admin/", admin.site.urls),
    path("api/audit-trail/", audit_trail_view, name="audit-trail"),
    path("api/contracts/status/", contract_status, name="contract-status"),
    path("api/analytics/rate-limits/", rate_limit_analytics_view, name="rate-limit-analytics"),
    path("api/ingest/", include("soroscan.ingest.urls")),
    path("graphql/", ThrottledGraphQLView.as_view(schema=schema)),
    # JWT Authentication
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # OpenAPI Schema & Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Silk profiling UI — available only when ENABLE_SILK is set
if getattr(settings, "ENABLE_SILK", False):
    urlpatterns += [path("silk/", include("silk.urls", namespace="silk"))]
