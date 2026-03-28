"""
Tests for the contract alias feature.
Covers: model field, serializer output, GraphQL query filter, admin display,
and list sorting by alias.
"""
import pytest
from unittest.mock import Mock

from soroscan.ingest.models import TrackedContract
from soroscan.ingest.schema import schema
from soroscan.ingest.serializers import TrackedContractSerializer
from .factories import TrackedContractFactory, UserFactory


def create_context_with_user(user):
    context = Mock()
    request = Mock()
    request.user = user
    context.request = request
    return context


@pytest.mark.django_db
class TestAliasModel:
    def test_alias_defaults_to_empty_string(self):
        contract = TrackedContractFactory()
        assert contract.alias == ""

    def test_alias_can_be_set(self):
        contract = TrackedContractFactory(alias="Token Transfer Contract")
        assert contract.alias == "Token Transfer Contract"

    def test_alias_max_length_is_256(self):
        field = TrackedContract._meta.get_field("alias")
        assert field.max_length == 256

    def test_alias_is_optional(self):
        field = TrackedContract._meta.get_field("alias")
        assert field.blank is True

    def test_display_name_returns_alias_when_set(self):
        contract = TrackedContractFactory(alias="My Alias")
        assert contract.display_name() == "My Alias"

    def test_display_name_returns_contract_id_when_no_alias(self):
        contract = TrackedContractFactory(alias="")
        assert contract.display_name() == contract.contract_id

    def test_str_uses_alias_when_set(self):
        contract = TrackedContractFactory(alias="Admin Registry")
        assert "Admin Registry" in str(contract)


@pytest.mark.django_db
class TestAliasSerializer:
    def test_serializer_includes_alias_field(self):
        contract = TrackedContractFactory(alias="My Token Contract")
        serializer = TrackedContractSerializer(contract)
        assert "alias" in serializer.data
        assert serializer.data["alias"] == "My Token Contract"

    def test_serializer_alias_empty_by_default(self):
        contract = TrackedContractFactory()
        serializer = TrackedContractSerializer(contract)
        assert serializer.data["alias"] == ""

    def test_serializer_can_write_alias(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user)
        request = Mock()
        request.user = user
        serializer = TrackedContractSerializer(
            contract,
            data={"alias": "New Alias", "name": contract.name, "contract_id": contract.contract_id},
            context={"request": request},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.alias == "New Alias"


@pytest.mark.django_db
class TestAliasGraphQL:
    def test_contracts_query_returns_alias(self):
        TrackedContractFactory(alias="Token Transfer Contract")
        query = """
            query {
                contracts {
                    contractId
                    alias
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert result.data["contracts"][0]["alias"] == "Token Transfer Contract"

    def test_contracts_query_filter_by_alias_substring(self):
        TrackedContractFactory(alias="Token Transfer Contract")
        TrackedContractFactory(alias="Admin Registry")
        TrackedContractFactory(alias="")

        query = """
            query {
                contracts(alias: "Token") {
                    alias
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["contracts"]) == 1
        assert result.data["contracts"][0]["alias"] == "Token Transfer Contract"

    def test_contracts_query_alias_filter_case_insensitive(self):
        TrackedContractFactory(alias="Token Transfer Contract")
        query = """
            query {
                contracts(alias: "token") {
                    alias
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["contracts"]) == 1

    def test_contracts_sorted_alias_first(self):
        # Contracts with alias should appear before those without
        TrackedContractFactory(alias="")
        TrackedContractFactory(alias="Alpha Contract")
        TrackedContractFactory(alias="Beta Contract")

        query = """
            query {
                contracts {
                    alias
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        contracts = result.data["contracts"]
        # First two should have aliases (non-empty)
        assert contracts[0]["alias"] != ""
        assert contracts[1]["alias"] != ""
        assert contracts[2]["alias"] == ""

    def test_update_contract_mutation_sets_alias(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user, alias="")
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    alias: "My Friendly Name"
                ) {{
                    contractId
                    alias
                }}
            }}
        """
        context = create_context_with_user(user)
        result = schema.execute_sync(mutation, context_value=context)
        assert result.errors is None
        assert result.data["updateContract"]["alias"] == "My Friendly Name"

        contract.refresh_from_db()
        assert contract.alias == "My Friendly Name"

    def test_update_contract_mutation_clears_alias(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user, alias="Old Alias")
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    alias: ""
                ) {{
                    alias
                }}
            }}
        """
        context = create_context_with_user(user)
        result = schema.execute_sync(mutation, context_value=context)
        assert result.errors is None
        assert result.data["updateContract"]["alias"] == ""
