"""Tests for fluent request builder pattern (issue #481)."""

import pytest
from unittest.mock import Mock, patch

from soroscan.builder import (
    EventQueryBuilder,
    AsyncEventQueryBuilder,
    ContractQueryBuilder,
    AsyncContractQueryBuilder,
)
from soroscan.client import SoroScanClient, AsyncSoroScanClient
from soroscan.models import PaginatedResponse, ContractEvent, TrackedContract


class TestEventQueryBuilder:
    """Tests for EventQueryBuilder."""

    def test_builder_initialization(self):
        """Test that builder initializes with default values."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        params = builder.build()
        assert params["ordering"] == "-timestamp"
        assert params["page"] == 1
        assert params["page_size"] == 50

    def test_filter_by_contract(self):
        """Test filtering by contract ID."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        result = builder.filter_by_contract("CCAAA123")
        assert result is builder  # Check method chaining
        
        params = builder.build()
        assert params["contract_id"] == "CCAAA123"

    def test_filter_by_event_type(self):
        """Test filtering by event type."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.filter_by_event_type("transfer")
        params = builder.build()
        assert params["event_type"] == "transfer"

    def test_filter_by_ledger(self):
        """Test filtering by specific ledger."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.filter_by_ledger(1000)
        params = builder.build()
        assert params["ledger"] == 1000

    def test_filter_by_ledger_range(self):
        """Test filtering by ledger range."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.filter_by_ledger_range(min=1000, max=2000)
        params = builder.build()
        assert params["ledger_min"] == 1000
        assert params["ledger_max"] == 2000

    def test_filter_by_validation_status(self):
        """Test filtering by validation status."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.filter_by_validation_status("passed")
        params = builder.build()
        assert params["validation_status"] == "passed"

    def test_order_by(self):
        """Test setting order field."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.order_by("ledger")
        params = builder.build()
        assert params["ordering"] == "ledger"

    def test_paginate(self):
        """Test pagination with limit and offset."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.paginate(limit=100, offset=200)
        params = builder.build()
        assert params["page_size"] == 100
        assert params["page"] == 3  # offset 200 / limit 100 + 1

    def test_page(self):
        """Test direct page setting."""
        client = Mock(spec=SoroScanClient)
        builder = EventQueryBuilder(client)
        
        builder.page(5, 25)
        params = builder.build()
        assert params["page"] == 5
        assert params["page_size"] == 25

    def test_method_chaining(self):
        """Test that all methods support chaining."""
        client = Mock(spec=SoroScanClient)
        builder = (EventQueryBuilder(client)
            .filter_by_contract("CCAAA123")
            .filter_by_event_type("transfer")
            .filter_by_ledger_range(min=1000, max=2000)
            .order_by("-ledger")
            .page(2, 100))
        
        params = builder.build()
        assert params["contract_id"] == "CCAAA123"
        assert params["event_type"] == "transfer"
        assert params["ledger_min"] == 1000
        assert params["ledger_max"] == 2000
        assert params["ordering"] == "-ledger"
        assert params["page"] == 2
        assert params["page_size"] == 100

    def test_execute_calls_client(self):
        """Test that execute calls the client with correct parameters."""
        client = Mock(spec=SoroScanClient)
        client.get_events.return_value = Mock(spec=PaginatedResponse)
        
        builder = (EventQueryBuilder(client)
            .filter_by_contract("CCAAA123")
            .filter_by_event_type("transfer")
            .execute())
        
        client.get_events.assert_called_once_with(
            contract_id="CCAAA123",
            event_type="transfer",
            ledger=None,
            ledger_min=None,
            ledger_max=None,
            validation_status=None,
            ordering="-timestamp",
            page=1,
            page_size=50,
        )

    def test_client_events_method(self):
        """Test that client.events() returns a builder."""
        client = SoroScanClient(base_url="https://api.test.com")
        builder = client.events()
        
        assert isinstance(builder, EventQueryBuilder)
        assert builder._client is client


class TestAsyncEventQueryBuilder:
    """Tests for AsyncEventQueryBuilder."""

    @pytest.mark.asyncio
    async def test_async_execute_calls_client(self):
        """Test that async execute calls the client with correct parameters."""
        client = Mock(spec=AsyncSoroScanClient)
        client.get_events.return_value = Mock(spec=PaginatedResponse)
        
        builder = AsyncEventQueryBuilder(client)
        builder.filter_by_contract("CCAAA123")
        
        await builder.execute()
        
        client.get_events.assert_called_once()

    def test_async_client_events_method(self):
        """Test that async client.events() returns a builder."""
        client = AsyncSoroScanClient(base_url="https://api.test.com")
        builder = client.events()
        
        assert isinstance(builder, AsyncEventQueryBuilder)
        assert builder._client is client


class TestContractQueryBuilder:
    """Tests for ContractQueryBuilder."""

    def test_filter_by_active(self):
        """Test filtering by active status."""
        client = Mock(spec=SoroScanClient)
        builder = ContractQueryBuilder(client)
        
        builder.filter_by_active(True)
        params = builder.build()
        assert params["is_active"] is True

    def test_search(self):
        """Test search functionality."""
        client = Mock(spec=SoroScanClient)
        builder = ContractQueryBuilder(client)
        
        builder.search("token")
        params = builder.build()
        assert params["search"] == "token"

    def test_execute_calls_client(self):
        """Test that execute calls the client with correct parameters."""
        client = Mock(spec=SoroScanClient)
        client.get_contracts.return_value = Mock(spec=PaginatedResponse)
        
        builder = (ContractQueryBuilder(client)
            .filter_by_active(True)
            .search("token")
            .page(2, 20)
            .execute())
        
        client.get_contracts.assert_called_once_with(
            is_active=True,
            search="token",
            page=2,
            page_size=20,
        )

    def test_client_contracts_method(self):
        """Test that client.contracts() returns a builder."""
        client = SoroScanClient(base_url="https://api.test.com")
        builder = client.contracts()
        
        assert isinstance(builder, ContractQueryBuilder)
        assert builder._client is client


class TestAsyncContractQueryBuilder:
    """Tests for AsyncContractQueryBuilder."""

    @pytest.mark.asyncio
    async def test_async_execute_calls_client(self):
        """Test that async execute calls the client with correct parameters."""
        client = Mock(spec=AsyncSoroScanClient)
        client.get_contracts.return_value = Mock(spec=PaginatedResponse)
        
        builder = AsyncContractQueryBuilder(client)
        builder.filter_by_active(True)
        
        await builder.execute()
        
        client.get_contracts.assert_called_once()

    def test_async_client_contracts_method(self):
        """Test that async client.contracts() returns a builder."""
        client = AsyncSoroScanClient(base_url="https://api.test.com")
        builder = client.contracts()
        
        assert isinstance(builder, AsyncContractQueryBuilder)
        assert builder._client is client


class TestBuilderIntegration:
    """Integration tests for builder pattern."""

    def test_complex_query_building(self):
        """Test building a complex query with multiple filters."""
        client = Mock(spec=SoroScanClient)
        
        query = (client.events()
            .filter_by_contract("CCAAA123")
            .filter_by_event_type("transfer")
            .filter_by_ledger_range(min=1000, max=2000)
            .filter_by_validation_status("passed")
            .order_by("-timestamp")
            .paginate(limit=50, offset=0)
            .build())
        
        assert query["contract_id"] == "CCAAA123"
        assert query["event_type"] == "transfer"
        assert query["ledger_min"] == 1000
        assert query["ledger_max"] == 2000
        assert query["validation_status"] == "passed"
        assert query["ordering"] == "-timestamp"
        assert query["page"] == 1
        assert query["page_size"] == 50

    def test_minimal_query_building(self):
        """Test building a minimal query with defaults."""
        client = Mock(spec=SoroScanClient)
        
        query = client.events().build()
        
        assert "contract_id" not in query
        assert "event_type" not in query
        assert query["ordering"] == "-timestamp"
        assert query["page"] == 1
        assert query["page_size"] == 50
