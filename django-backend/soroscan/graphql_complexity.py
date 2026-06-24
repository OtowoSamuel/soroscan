"""
GraphQL query complexity analysis.

Estimates resource cost of incoming queries and rejects queries that exceed
configured limits before resolvers execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    IntValueNode,
    OperationDefinitionNode,
    parse,
)

# Arguments that scale list-fetch cost.
_LIST_SIZE_ARGS = frozenset({"first", "last", "limit", "take"})

# Default multiplier when a list-size argument is omitted.
_DEFAULT_LIST_SIZE = 10

# Per-field base cost.
_FIELD_COST = 1


@dataclass(frozen=True)
class ComplexityResult:
    """Outcome of complexity analysis for a single operation."""

    score: int
    max_allowed: int

    @property
    def exceeded(self) -> bool:
        return self.score > self.max_allowed


def _int_from_value_node(node: Any) -> int | None:
    if isinstance(node, IntValueNode):
        try:
            return int(node.value)
        except (TypeError, ValueError):
            return None
    return None


def _explicit_list_size(field: FieldNode) -> int | None:
    for argument in field.arguments:
        if argument.name.value not in _LIST_SIZE_ARGS:
            continue
        value = _int_from_value_node(argument.value)
        if value is not None and value > 0:
            return value
    return None


def _field_multiplier(field: FieldNode, parent_multiplier: int) -> int:
    explicit = _explicit_list_size(field)
    if explicit is not None:
        return parent_multiplier * explicit
    if parent_multiplier == 1 and field.selection_set is not None:
        return _DEFAULT_LIST_SIZE
    return parent_multiplier


class _ComplexityVisitor:
    """Walk the operation AST and accumulate a complexity score."""

    def __init__(self, fragments: dict[str, FragmentDefinitionNode]):
        self._fragments = fragments
        self.score = 0

    def _visit_selection_set(self, selection_set, parent_multiplier: int) -> None:
        if selection_set is None:
            return

        for selection in selection_set.selections:
            if isinstance(selection, FieldNode):
                multiplier = _field_multiplier(selection, parent_multiplier)
                self.score += _FIELD_COST * multiplier
                self._visit_selection_set(selection.selection_set, multiplier)
            elif isinstance(selection, InlineFragmentNode):
                self._visit_selection_set(selection.selection_set, parent_multiplier)
            elif isinstance(selection, FragmentSpreadNode):
                fragment = self._fragments.get(selection.name.value)
                if fragment is not None:
                    self._visit_selection_set(fragment.selection_set, parent_multiplier)


def calculate_complexity(query: str, *, max_allowed: int) -> ComplexityResult:
    """
    Parse *query* and return its estimated complexity score.

    Raises ``GraphQLError`` when the document cannot be parsed.
    """
    document = parse(query)
    fragments: dict[str, FragmentDefinitionNode] = {}
    operation: OperationDefinitionNode | None = None

    for definition in document.definitions:
        if isinstance(definition, FragmentDefinitionNode):
            fragments[definition.name.value] = definition
        elif isinstance(definition, OperationDefinitionNode) and operation is None:
            operation = definition

    if operation is None:
        return ComplexityResult(score=0, max_allowed=max_allowed)

    visitor = _ComplexityVisitor(fragments)
    visitor._visit_selection_set(operation.selection_set, parent_multiplier=1)
    return ComplexityResult(score=visitor.score, max_allowed=max_allowed)


def complexity_error_message(result: ComplexityResult) -> str:
    return (
        f"Query complexity {result.score} exceeds the maximum allowed "
        f"complexity of {result.max_allowed}. Reduce nested fields or "
        f"lower pagination arguments such as first/limit."
    )
