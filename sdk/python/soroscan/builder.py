"""Fluent request builder pattern for SoroScan SDK (issue #481)."""

from typing import Any, Literal, TYPE_CHECKING

from soroscan.models import ContractEvent, PaginatedResponse, TrackedContract

if TYPE_CHECKING:
    from soroscan.client import SoroScanClient, AsyncSoroScanClient


class EventQueryBuilder:
    """
    Fluent builder for constructing event queries.
    
    Example:
        >>> client = SoroScanClient()
        >>> events = (client.events()
        ...     .filter_by_contract("CCAAA...")
        ...     .filter_by_event_type("transfer")
        ...     .filter_by_ledger_range(min=1000, max=2000)
        ...     .order_by("-timestamp")
        ...     .paginate(limit=50, offset=0)
        ...     .execute())
    """
    
    def __init__(self, client: "SoroScanClient") -> None:
        """Initialize the builder with a client instance."""
        self._client = client
        self._contract_id: str | None = None
        self._event_type: str | None = None
        self._ledger: int | None = None
        self._ledger_min: int | None = None
        self._ledger_max: int | None = None
        self._validation_status: Literal["passed", "failed"] | None = None
        self._ordering: str = "-timestamp"
        self._page: int = 1
        self._page_size: int = 50
    
    def filter_by_contract(self, contract_id: str) -> "EventQueryBuilder":
        """
        Filter events by contract address.
        
        Args:
            contract_id: Stellar contract address (C...)
            
        Returns:
            Self for method chaining
        """
        self._contract_id = contract_id
        return self
    
    def filter_by_event_type(self, event_type: str) -> "EventQueryBuilder":
        """
        Filter events by event type.
        
        Args:
            event_type: Event type name (e.g., "transfer", "swap")
            
        Returns:
            Self for method chaining
        """
        self._event_type = event_type
        return self
    
    def filter_by_ledger(self, ledger: int) -> "EventQueryBuilder":
        """
        Filter events by specific ledger sequence.
        
        Args:
            ledger: Ledger sequence number
            
        Returns:
            Self for method chaining
        """
        self._ledger = ledger
        return self
    
    def filter_by_ledger_range(
        self, 
        min: int | None = None, 
        max: int | None = None
    ) -> "EventQueryBuilder":
        """
        Filter events by ledger range.
        
        Args:
            min: Minimum ledger sequence (inclusive)
            max: Maximum ledger sequence (inclusive)
            
        Returns:
            Self for method chaining
        """
        if min is not None:
            self._ledger_min = min
        if max is not None:
            self._ledger_max = max
        return self
    
    def filter_by_validation_status(
        self, 
        status: Literal["passed", "failed"]
    ) -> "EventQueryBuilder":
        """
        Filter events by validation status.
        
        Args:
            status: Validation status ("passed" or "failed")
            
        Returns:
            Self for method chaining
        """
        self._validation_status = status
        return self
    
    def order_by(self, field: str) -> "EventQueryBuilder":
        """
        Set the ordering field.
        
        Args:
            field: Field name to order by (prefix with - for descending)
                   Examples: "timestamp", "-timestamp", "ledger", "-ledger"
            
        Returns:
            Self for method chaining
        """
        self._ordering = field
        return self
    
    def paginate(self, limit: int = 50, offset: int = 0) -> "EventQueryBuilder":
        """
        Set pagination parameters.
        
        Args:
            limit: Number of results per page (page_size)
            offset: Number of results to skip (converted to page number)
            
        Returns:
            Self for method chaining
        """
        self._page_size = limit
        self._page = (offset // limit) + 1 if limit > 0 else 1
        return self
    
    def page(self, page: int, page_size: int = 50) -> "EventQueryBuilder":
        """
        Set page number and page size directly.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of results per page
            
        Returns:
            Self for method chaining
        """
        self._page = page
        self._page_size = page_size
        return self
    
    def execute(self) -> PaginatedResponse[ContractEvent]:
        """
        Execute the query and return results.
        
        Returns:
            Paginated response containing events
        """
        return self._client.get_events(
            contract_id=self._contract_id,
            event_type=self._event_type,
            ledger=self._ledger,
            ledger_min=self._ledger_min,
            ledger_max=self._ledger_max,
            validation_status=self._validation_status,
            ordering=self._ordering,
            page=self._page,
            page_size=self._page_size,
        )
    
    def build(self) -> dict[str, Any]:
        """
        Build and return the query parameters without executing.
        
        Returns:
            Dictionary of query parameters
        """
        params: dict[str, Any] = {
            "ordering": self._ordering,
            "page": self._page,
            "page_size": self._page_size,
        }
        if self._contract_id:
            params["contract_id"] = self._contract_id
        if self._event_type:
            params["event_type"] = self._event_type
        if self._ledger is not None:
            params["ledger"] = self._ledger
        if self._ledger_min is not None:
            params["ledger_min"] = self._ledger_min
        if self._ledger_max is not None:
            params["ledger_max"] = self._ledger_max
        if self._validation_status:
            params["validation_status"] = self._validation_status
        return params


class AsyncEventQueryBuilder:
    """
    Async fluent builder for constructing event queries.
    
    Example:
        >>> client = AsyncSoroScanClient()
        >>> events = await (client.events()
        ...     .filter_by_contract("CCAAA...")
        ...     .filter_by_event_type("transfer")
        ...     .execute())
    """
    
    def __init__(self, client: "AsyncSoroScanClient") -> None:
        """Initialize the builder with an async client instance."""
        self._client = client
        self._contract_id: str | None = None
        self._event_type: str | None = None
        self._ledger: int | None = None
        self._ledger_min: int | None = None
        self._ledger_max: int | None = None
        self._validation_status: Literal["passed", "failed"] | None = None
        self._ordering: str = "-timestamp"
        self._page: int = 1
        self._page_size: int = 50
    
    def filter_by_contract(self, contract_id: str) -> "AsyncEventQueryBuilder":
        """Filter events by contract address."""
        self._contract_id = contract_id
        return self
    
    def filter_by_event_type(self, event_type: str) -> "AsyncEventQueryBuilder":
        """Filter events by event type."""
        self._event_type = event_type
        return self
    
    def filter_by_ledger(self, ledger: int) -> "AsyncEventQueryBuilder":
        """Filter events by specific ledger sequence."""
        self._ledger = ledger
        return self
    
    def filter_by_ledger_range(
        self, 
        min: int | None = None, 
        max: int | None = None
    ) -> "AsyncEventQueryBuilder":
        """Filter events by ledger range."""
        if min is not None:
            self._ledger_min = min
        if max is not None:
            self._ledger_max = max
        return self
    
    def filter_by_validation_status(
        self, 
        status: Literal["passed", "failed"]
    ) -> "AsyncEventQueryBuilder":
        """Filter events by validation status."""
        self._validation_status = status
        return self
    
    def order_by(self, field: str) -> "AsyncEventQueryBuilder":
        """Set the ordering field."""
        self._ordering = field
        return self
    
    def paginate(self, limit: int = 50, offset: int = 0) -> "AsyncEventQueryBuilder":
        """Set pagination parameters."""
        self._page_size = limit
        self._page = (offset // limit) + 1 if limit > 0 else 1
        return self
    
    def page(self, page: int, page_size: int = 50) -> "AsyncEventQueryBuilder":
        """Set page number and page size directly."""
        self._page = page
        self._page_size = page_size
        return self
    
    async def execute(self) -> PaginatedResponse[ContractEvent]:
        """Execute the query and return results."""
        return await self._client.get_events(
            contract_id=self._contract_id,
            event_type=self._event_type,
            ledger=self._ledger,
            ledger_min=self._ledger_min,
            ledger_max=self._ledger_max,
            validation_status=self._validation_status,
            ordering=self._ordering,
            page=self._page,
            page_size=self._page_size,
        )
    
    def build(self) -> dict[str, Any]:
        """Build and return the query parameters without executing."""
        params: dict[str, Any] = {
            "ordering": self._ordering,
            "page": self._page,
            "page_size": self._page_size,
        }
        if self._contract_id:
            params["contract_id"] = self._contract_id
        if self._event_type:
            params["event_type"] = self._event_type
        if self._ledger is not None:
            params["ledger"] = self._ledger
        if self._ledger_min is not None:
            params["ledger_min"] = self._ledger_min
        if self._ledger_max is not None:
            params["ledger_max"] = self._ledger_max
        if self._validation_status:
            params["validation_status"] = self._validation_status
        return params


class ContractQueryBuilder:
    """
    Fluent builder for constructing contract queries.
    
    Example:
        >>> client = SoroScanClient()
        >>> contracts = (client.contracts()
        ...     .filter_by_active(True)
        ...     .search("token")
        ...     .page(1, 20)
        ...     .execute())
    """
    
    def __init__(self, client: "SoroScanClient") -> None:
        """Initialize the builder with a client instance."""
        self._client = client
        self._is_active: bool | None = None
        self._search: str | None = None
        self._page: int = 1
        self._page_size: int = 50
    
    def filter_by_active(self, is_active: bool) -> "ContractQueryBuilder":
        """
        Filter contracts by active status.
        
        Args:
            is_active: True for active contracts, False for inactive
            
        Returns:
            Self for method chaining
        """
        self._is_active = is_active
        return self
    
    def search(self, query: str) -> "ContractQueryBuilder":
        """
        Search contracts by name or contract ID.
        
        Args:
            query: Search query string
            
        Returns:
            Self for method chaining
        """
        self._search = query
        return self
    
    def page(self, page: int, page_size: int = 50) -> "ContractQueryBuilder":
        """
        Set page number and page size.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of results per page
            
        Returns:
            Self for method chaining
        """
        self._page = page
        self._page_size = page_size
        return self
    
    def execute(self) -> PaginatedResponse[TrackedContract]:
        """
        Execute the query and return results.
        
        Returns:
            Paginated response containing contracts
        """
        return self._client.get_contracts(
            is_active=self._is_active,
            search=self._search,
            page=self._page,
            page_size=self._page_size,
        )
    
    def build(self) -> dict[str, Any]:
        """
        Build and return the query parameters without executing.
        
        Returns:
            Dictionary of query parameters
        """
        params: dict[str, Any] = {
            "page": self._page,
            "page_size": self._page_size,
        }
        if self._is_active is not None:
            params["is_active"] = self._is_active
        if self._search:
            params["search"] = self._search
        return params


class AsyncContractQueryBuilder:
    """Async fluent builder for constructing contract queries."""
    
    def __init__(self, client: "AsyncSoroScanClient") -> None:
        """Initialize the builder with an async client instance."""
        self._client = client
        self._is_active: bool | None = None
        self._search: str | None = None
        self._page: int = 1
        self._page_size: int = 50
    
    def filter_by_active(self, is_active: bool) -> "AsyncContractQueryBuilder":
        """Filter contracts by active status."""
        self._is_active = is_active
        return self
    
    def search(self, query: str) -> "AsyncContractQueryBuilder":
        """Search contracts by name or contract ID."""
        self._search = query
        return self
    
    def page(self, page: int, page_size: int = 50) -> "AsyncContractQueryBuilder":
        """Set page number and page size."""
        self._page = page
        self._page_size = page_size
        return self
    
    async def execute(self) -> PaginatedResponse[TrackedContract]:
        """Execute the query and return results."""
        return await self._client.get_contracts(
            is_active=self._is_active,
            search=self._search,
            page=self._page,
            page_size=self._page_size,
        )
    
    def build(self) -> dict[str, Any]:
        """Build and return the query parameters without executing."""
        params: dict[str, Any] = {
            "page": self._page,
            "page_size": self._page_size,
        }
        if self._is_active is not None:
            params["is_active"] = self._is_active
        if self._search:
            params["search"] = self._search
        return params
