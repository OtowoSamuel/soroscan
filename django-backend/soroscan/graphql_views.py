"""
Custom GraphQL views with rate limiting and introspection control.
"""
import json

from django.conf import settings
from django.http import JsonResponse
from graphql.error import GraphQLError
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from strawberry.django.views import GraphQLView

from soroscan.graphql_complexity import calculate_complexity, complexity_error_message
from soroscan.throttles import IngestRateThrottle

_INTROSPECTION_FIELDS = {"__schema", "__type", "__typename"}


def _parse_request_body(body: bytes) -> dict:
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, AttributeError):
        return {}


def _is_introspection_query(body: bytes) -> bool:
    """Return True if the request body contains a GraphQL introspection query."""
    query = _parse_request_body(body).get("query", "")
    return any(field in query for field in _INTROSPECTION_FIELDS)


def _evaluate_query_complexity(body: bytes):
    """
    Return a ComplexityResult for POST bodies with a query, or None otherwise.

    Parse failures are returned as a JsonResponse for the caller to return.
    """
    query = _parse_request_body(body).get("query", "")
    if not query:
        return None

    max_allowed = int(getattr(settings, "GRAPHQL_MAX_COMPLEXITY", 1000))
    try:
        return calculate_complexity(query, max_allowed=max_allowed)
    except GraphQLError as exc:
        return JsonResponse({"errors": [{"message": str(exc)}]}, status=400)


class ThrottledGraphQLView(GraphQLView):
    """
    GraphQL view with rate limiting and optional introspection blocking.

    Set GRAPHQL_INTROSPECTION_ENABLED=False (default in production) to reject
    introspection queries with a 403 and a clear error message.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.anon_throttle = AnonRateThrottle()
        self.user_throttle = UserRateThrottle()
        self.ingest_throttle = IngestRateThrottle()

    def get_throttles(self, request):
        """Return list of throttle instances to check."""
        return [self.anon_throttle, self.user_throttle]

    def check_throttles(self, request):
        """Check if request should be throttled."""
        for throttle in self.get_throttles(request):
            if not throttle.allow_request(request, self):
                self.throttle_failure()

    def throttle_failure(self):
        """Handle throttle failure — raise 429."""
        from rest_framework.exceptions import Throttled

        raise Throttled(detail="Rate limit exceeded. Please try again later.")

    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to add throttling and introspection checks."""
        self.check_throttles(request)

        complexity_result = None
        if request.method == "POST":
            body = request.body
            complexity_eval = _evaluate_query_complexity(body)
            if isinstance(complexity_eval, JsonResponse):
                return complexity_eval
            complexity_result = complexity_eval

            introspection_enabled = getattr(
                settings, "GRAPHQL_INTROSPECTION_ENABLED", True
            )
            if not introspection_enabled and _is_introspection_query(body):
                return JsonResponse(
                    {
                        "errors": [
                            {
                                "message": (
                                    "GraphQL introspection is disabled in production. "
                                    "Set GRAPHQL_INTROSPECTION_ENABLED=True to enable it."
                                )
                            }
                        ]
                    },
                    status=403,
                )

            if complexity_result is not None and complexity_result.exceeded:
                return JsonResponse(
                    {
                        "errors": [
                            {"message": complexity_error_message(complexity_result)}
                        ],
                        "extensions": {
                            "complexity": {
                                "score": complexity_result.score,
                                "maxAllowed": complexity_result.max_allowed,
                            }
                        },
                    },
                    status=400,
                )

        response = super().dispatch(request, *args, **kwargs)

        if complexity_result is not None and hasattr(response, "__setitem__"):
            response["X-GraphQL-Complexity"] = str(complexity_result.score)
            response["X-GraphQL-Complexity-Limit"] = str(
                complexity_result.max_allowed
            )

        return response
