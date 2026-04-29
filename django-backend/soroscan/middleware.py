"""
Middleware for request-scoped log context (request_id) and slow query logging.
"""
import json
import logging
import time
import uuid

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

from .log_context import set_request_id

logger = logging.getLogger(__name__)
slow_query_logger = logging.getLogger("soroscan.slow_queries")


class RequestIdMiddleware:
    """Set request_id on the request and in log context for the request lifecycle."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or getattr(request, "request_id", None) or uuid.uuid4().hex
        request.request_id = request_id
        set_request_id(request_id)
        
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        
        if response.status_code >= 400 and response.get("Content-Type", "").startswith("application/json"):
            if not getattr(response, "streaming", False):
                try:
                    data = json.loads(response.content)
                    if isinstance(data, dict):
                        data["request_id"] = request_id
                        new_content = json.dumps(data).encode("utf-8")
                        response.content = new_content
                        if "Content-Length" in response:
                            response["Content-Length"] = str(len(new_content))
                except (json.JSONDecodeError, AttributeError):
                    pass
                    
        return response


class PlatformVersionMiddleware:
    """Attach platform version metadata to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-SoroScan-Version"] = getattr(settings, "SOFTWARE_VERSION", "unknown")
        return response


class ReverseProxyFixedIPMiddleware:
    """
    Middleware to handle rate limiting behind a reverse proxy.

    When running behind a reverse proxy (e.g., Nginx, Cloudflare),
    the REMOTE_ADDR will always be the proxy's IP. This middleware
    extracts the original client IP from X-Forwarded-For header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
            request.META["REMOTE_ADDR"] = client_ip
        return self.get_response(request)


class SlowQueryMiddleware:
    """
    Wrap every DB execute call to log queries that exceed
    LOGGING_SLOW_QUERIES_THRESHOLD_MS (default 100 ms) to the
    ``soroscan.slow_queries`` logger, which writes to a daily-rotated file.

    Overhead is negligible (<1 µs per query for the monotonic clock call)
    and the wrapper is only active when the logger is configured.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms: int = getattr(settings, "LOGGING_SLOW_QUERIES_THRESHOLD_MS", 100)

    def __call__(self, request):
        threshold = self.threshold_ms

        def _execute(execute, sql, params, many, context):
            start = time.monotonic()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = (time.monotonic() - start) * 1000
                if duration_ms >= threshold:
                    # Convert params to a serializable format or stringify it to avoid log formatting errors
                    safe_params = str(params)[:1000] if params else ""
                    slow_query_logger.warning(
                        "Slow query (%dms): %s\nParams: %s",
                        int(duration_ms),
                        (sql or "")[:1000],
                        safe_params,
                        extra={
                            "duration_ms": round(duration_ms, 2),
                            "sql": (sql or "")[:1000],
                            "params": safe_params,
                            "request_path": request.path,
                        },
                    )

        with connection.execute_wrapper(_execute):
            response = self.get_response(request)

        # Forward X-RateLimit-* headers set by APIKeyThrottle
        headers = getattr(request, "_api_key_throttle_headers", None)
        if headers and hasattr(response, "__setitem__"):
            for name, value in headers.items():
                response[name] = value

        return response

class RequestBodySizeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We check this at the very beginning of the __call__
        if request.method == "POST":
            max_size = getattr(settings, "MAX_REQUEST_BODY_SIZE", 10485760)
            try:
                content_length = int(request.META.get('CONTENT_LENGTH', 0))
                if content_length > max_size:
                    logger.warning("Payload Too Large: %s bytes", content_length)
                    return JsonResponse(
                        {"error": "Payload Too Large", "limit": max_size},
                        status=413
                    )
            except (ValueError, TypeError):
                pass
        
        return self.get_response(request)
        
class MaintenanceModeMiddleware:
    """Return 503 for all non-admin routes when MAINTENANCE_MODE=True."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "MAINTENANCE_MODE", False) and not request.path.startswith("/admin"):
            return JsonResponse(
                {"error": "Service temporarily unavailable. Please try again later."},
                status=503,
            )
        return self.get_response(request)


class ApiDeprecationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        deprecated_endpoints = getattr(settings, "DEPRECATED_ENDPOINTS", {})
        
        # Normalize request path: remove leading/trailing slashes
        norm_request_path = request.path.strip("/")
        
        for path, config in deprecated_endpoints.items():
            # Normalize config path
            if path.strip("/") == norm_request_path:
                response["Deprecation"] = "true"
                response["Sunset"] = config.get("sunset", "")
                response["Link"] = f'<{config.get("replacement", "")}>; rel="replacement"'
                break
        return response