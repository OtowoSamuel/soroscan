"""
Custom throttle classes for SoroScan API rate limiting.
"""
import logging
import time

from django.core.cache import cache
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle

logger = logging.getLogger(__name__)

# Header names returned on every response
HEADER_LIMIT = "X-RateLimit-Limit"
HEADER_REMAINING = "X-RateLimit-Remaining"
HEADER_RESET = "X-RateLimit-Reset"

# TTL of Redis counter bucket (1 hour)
_BUCKET_TTL = 3600


class APIKeyThrottle(BaseThrottle):
    """
    Per-API-key tiered rate limiting with Redis counters.

    Reads the ``Authorization: ApiKey <token>`` header or the ``?api_key=``
    query parameter.  Falls through transparently (allow) when no API key is
    present so that the standard anon/user throttles still apply.

    Sets ``request._api_key_headers`` dict so the RateLimitHeaderMixin can
    populate X-RateLimit-* response headers.
    """

    CACHE_PREFIX = "soroscan_api_key_quota"

    def get_ident(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.lower().startswith("apikey "):
            return auth[7:].strip()
        return request.GET.get("api_key") or request.POST.get("api_key")

    def _cache_key(self, api_key_id: int) -> str:
        # Bucket resets at the start of every calendar hour
        bucket_hour = int(time.time()) // _BUCKET_TTL
        return f"{self.CACHE_PREFIX}:{api_key_id}:{bucket_hour}"

    def allow_request(self, request, view):
        key_str = self.get_ident(request)
        if not key_str:
            # No API key — let other throttles handle this request
            return True

        from soroscan.ingest.models import APIKey, ContractQuota

        try:
            api_key = APIKey.objects.select_related("user").get(
                key=key_str, is_active=True
            )
        except APIKey.DoesNotExist:
            # Invalid / revoked key → reject
            self._set_headers(request, limit=0, remaining=0, reset=self._next_reset())
            return False

        # Determine effective quota (contract-level override wins when lower)
        quota = api_key.quota_per_hour
        contract_id = (
            view.kwargs.get("contract_id")
            or request.GET.get("contract_id")
            or (request.data.get("contract_id") if hasattr(request, "data") else None)
        )
        if contract_id:
            override = (
                ContractQuota.objects.filter(
                    api_key=api_key,
                    contract__contract_id=contract_id,
                )
                .values_list("quota_per_hour", flat=True)
                .first()
            )
            if override is not None:
                quota = min(quota, override)

        cache_key = self._cache_key(api_key.id)
        count = cache.get(cache_key, 0)
        remaining = max(0, quota - count)
        reset_ts = self._next_reset()

        if count >= quota:
            self._set_headers(request, limit=quota, remaining=0, reset=reset_ts)
            logger.warning(
                "API key %s quota exhausted (%d/%d req/hr)",
                api_key.id,
                count,
                quota,
                extra={"api_key_id": api_key.id},
            )
            return False

        # Increment atomically via add+incr pattern
        if not cache.add(cache_key, 1, timeout=_BUCKET_TTL):
            cache.incr(cache_key)

        # Stamp last_used_at without blocking request (fire-and-forget via ORM)
        from django.utils import timezone

        APIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())

        self._set_headers(request, limit=quota, remaining=remaining - 1, reset=reset_ts)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next_reset() -> int:
        """Unix timestamp of the start of the next 1-hour bucket."""
        now = int(time.time())
        return (now // _BUCKET_TTL + 1) * _BUCKET_TTL

    @staticmethod
    def _set_headers(request, *, limit: int, remaining: int, reset: int) -> None:
        request._api_key_throttle_headers = {
            HEADER_LIMIT: str(limit),
            HEADER_REMAINING: str(remaining),
            HEADER_RESET: str(reset),
        }

    def wait(self):
        return max(0.0, self._next_reset() - time.time())


class IngestRateThrottle(SimpleRateThrottle):
    """
    Stricter rate limit for the ingest endpoint (POST /api/ingest/record/).
    """

    scope = "ingest"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def throttle_failure(self):
        return None  # Use default DRF throttle failure behaviour


class GraphQLRateThrottle(SimpleRateThrottle):
    """
    Rate limit specifically for GraphQL endpoints.
    """

    scope = "graphql"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
