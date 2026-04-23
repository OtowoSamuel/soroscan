"""
Bug condition exploration test for the ingest app migration graph conflict.

This test file ensures that the migration graph is consistent and has a single leaf node.
The conflict between 0027_merge_final_leaf_nodes and 0029_contractmetadata has been resolved.

Validates: Requirements 2.1, 2.2
"""

import pytest
from django.db.migrations.loader import MigrationLoader


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests():
    """Override root conftest fixture — this test does not need DB access."""
    pass


def test_single_leaf_node():
    """
    Assert the ingest migration graph has exactly one leaf node.

    The current leaf is '0031_trackedcontract_json_schema_and_webhook_filters'
    which depends on '0030_webhook_backoff_strategy'.
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)

    # leaf_nodes(app) returns nodes that no other migration depends on
    leaf_nodes = loader.graph.leaf_nodes(app="ingest")

    assert len(leaf_nodes) == 1, (
        f"Expected 1 leaf node for 'ingest', found {len(leaf_nodes)}: {leaf_nodes}"
    )
    assert leaf_nodes[0][1] == "0031_trackedcontract_json_schema_and_webhook_filters", (
        "Expected leaf node '0031_trackedcontract_json_schema_and_webhook_filters', "
        f"got '{leaf_nodes[0][1]}'"
    )


# ---------------------------------------------------------------------------
# Preservation property tests (Task 2)
# These tests PASS on unfixed code — they establish the baseline behavior
# that must be preserved after the fix is applied.
# Validates: Requirements 3.1, 3.2, 3.3
# ---------------------------------------------------------------------------


def test_dependency_order_preserved():
    """
    For every migration in the ingest app (0001–0026), assert all its declared
    dependencies appear in the graph (i.e., the dependency chain is intact).

    **Validates: Requirements 3.3**
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    graph = loader.graph

    # Collect all node keys present in the graph for the ingest app
    ingest_nodes = {key for key in graph.nodes if key[0] == "ingest"}

    # For every ingest migration, check that each of its ingest-app dependencies
    # is also present as a node in the graph.
    for node_key in ingest_nodes:
        migration = graph.nodes[node_key]
        for dep_app, dep_name in migration.dependencies:
            if dep_app == "ingest":
                assert (dep_app, dep_name) in ingest_nodes, (
                    f"Migration {node_key} declares dependency ({dep_app}, {dep_name}) "
                    f"which is missing from the migration graph."
                )


def test_migration_dependency_chain_intact():
    """
    Assert that key migrations in the chain exist as nodes in the graph:
    0001_initial, 0024_merge_20260328_1903, 0025_merge_20260329_0125,
    0026_merge_20260329_0027.

    This confirms the dependency chain below the conflict tip is intact.

    **Validates: Requirements 3.3**
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    graph = loader.graph

    required_nodes = [
        ("ingest", "0001_initial"),
        ("ingest", "0024_merge_20260328_1903"),
        ("ingest", "0025_merge_20260329_0125"),
        ("ingest", "0026_merge_20260329_0027"),
    ]

    for node_key in required_nodes:
        assert node_key in graph.nodes, (
            f"Expected migration node {node_key} to exist in the migration graph, "
            f"but it was not found."
        )
