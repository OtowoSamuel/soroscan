"""Tests for GraphQL query complexity analysis (issue #505)."""
import json
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from soroscan.graphql_complexity import (
    calculate_complexity,
    complexity_error_message,
)
from soroscan.graphql_views import ThrottledGraphQLView, _evaluate_query_complexity


class CalculateComplexityTest(TestCase):
    def test_simple_query_has_low_complexity(self):
        result = calculate_complexity(
            "{ contracts { id name } }",
            max_allowed=1000,
        )
        self.assertEqual(result.score, 30)
        self.assertFalse(result.exceeded)

    def test_pagination_argument_increases_complexity(self):
        result = calculate_complexity(
            "{ events(first: 100) { id } }",
            max_allowed=1000,
        )
        self.assertEqual(result.score, 200)

    def test_nested_fields_multiply_complexity(self):
        query = """
        {
          contracts {
            id
            events(first: 5) {
              id
              payload
            }
          }
        }
        """
        result = calculate_complexity(query, max_allowed=1000)
        self.assertEqual(result.score, 170)

    def test_exceeded_flag(self):
        result = calculate_complexity(
            "{ events(first: 500) { id payload ledger } }",
            max_allowed=100,
        )
        self.assertTrue(result.exceeded)

    def test_error_message_includes_scores(self):
        result = calculate_complexity(
            "{ events(first: 500) { id } }",
            max_allowed=10,
        )
        message = complexity_error_message(result)
        self.assertIn("1000", message)
        self.assertIn("10", message)


class GraphQLViewComplexityTest(TestCase):
    def _make_view(self):
        view = ThrottledGraphQLView(schema=MagicMock())
        view.check_throttles = lambda request: None
        return view

    def test_rejects_expensive_query_before_execution(self):
        factory = RequestFactory()
        body = json.dumps(
            {"query": "{ events(first: 500) { id payload ledger } }"}
        ).encode()
        request = factory.post(
            "/graphql/",
            data=body,
            content_type="application/json",
        )
        view = self._make_view()

        with patch("soroscan.graphql_views.settings") as mock_settings:
            mock_settings.GRAPHQL_MAX_COMPLEXITY = 50
            mock_settings.GRAPHQL_INTROSPECTION_ENABLED = True
            response = view.dispatch(request)

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content)
        self.assertIn("complexity", payload["errors"][0]["message"].lower())
        self.assertEqual(payload["extensions"]["complexity"]["score"], 2000)

    def test_allows_query_and_sets_complexity_headers(self):
        factory = RequestFactory()
        body = json.dumps({"query": "{ contracts { id } }"}).encode()
        request = factory.post(
            "/graphql/",
            data=body,
            content_type="application/json",
        )
        view = self._make_view()

        with patch("soroscan.graphql_views.settings") as mock_settings:
            mock_settings.GRAPHQL_MAX_COMPLEXITY = 1000
            mock_settings.GRAPHQL_INTROSPECTION_ENABLED = True
            with patch(
                "strawberry.django.views.GraphQLView.dispatch",
                return_value=HttpResponse("{}", status=200, content_type="application/json"),
            ):
                response = view.dispatch(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-GraphQL-Complexity"], "20")
        self.assertEqual(response["X-GraphQL-Complexity-Limit"], "1000")

    def test_evaluate_returns_none_for_empty_body(self):
        self.assertIsNone(_evaluate_query_complexity(b"{}"))
