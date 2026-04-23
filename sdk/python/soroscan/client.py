"""SoroScan API client implementations."""

from typing import Any, Literal
from urllib.parse import urljoin

import httpx
from pydantic import TypeAdapter

from soroscan.exceptions import (
    SoroScanAPIError,
    SoroScanAuthError,
    SoroScanNotFoundError,
    SoroScanRateLimitError,
    SoroScanValidationError,
)
from soroscan.models import (
    ContractEvent,
    ContractStats,
    PaginatedResponse,
    RecordEventRequest,
    RecordEventResponse,
    TrackedContract,
    WebhookSubscription,
)


class SoroScanClient:
    """
    Synchronous client for the SoroScan API.

    Example:
        >>> client = SoroScanClient(base_url="https://api.soroscan.io", api_key="your-key")
        >>> events = client.get_events(contract_id="CCAAA...", first=50)
    """

    def __init__(
        self,
        base_url: str = "https://api.soroscan.io",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the SoroScan client.

        Args:
            base_url: Base URL of the SoroScan API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> "SoroScanClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def _get_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response and raise appropriate exceptions."""
        if response.status_code == 200 or response.status_code == 201:
            return response.json()  # type: ignore[no-any-return]
        elif response.status_code == 202:
            return response.json()  # type: ignore[no-any-return]

        # Error handling
        try:
            error_data = response.json()
        except Exception:
            error_data = {}

        error_message = error_data.get("detail") or error_data.get("error") or response.text

        if response.status_code == 400:
            raise SoroScanValidationError(error_message, response.status_code, error_data)
        elif response.status_code == 401 or response.status_code == 403:
            raise SoroScanAuthError(error_message, response.status_code, error_data)
        elif response.status_code == 404:
            raise SoroScanNotFoundError(error_message, response.status_code, error_data)
        elif response.status_code == 429:
            raise SoroScanRateLimitError(error_message, response.status_code, error_data)
        else:
            raise SoroScanAPIError(error_message, response.status_code, error_data)

    def get_contracts(
        self,
        is_active: bool | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[TrackedContract]:
        """
        List tracked contracts.

        Args:
            is_active: Filter by active status
            search: Search by name or contract_id
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated list of tracked contracts
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if is_active is not None:
            params["is_active"] = is_active
        if search:
            params["search"] = search

        url = urljoin(self.base_url, "/api/contracts/")
        response = self._client.get(url, headers=self._get_headers(), params=params)
        data = self._handle_response(response)

        adapter = TypeAdapter(PaginatedResponse[TrackedContract])
        return adapter.validate_python(data)

    def get_contract(self, contract_id: str) -> TrackedContract:
        """
        Get a specific contract by ID.

        Args:
            contract_id: Contract database ID or contract address

        Returns:
            Contract details
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/")
        response = self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return TrackedContract.model_validate(data)

    def create_contract(
        self,
        contract_id: str,
        name: str,
        description: str = "",
        abi_schema: dict[str, Any] | None = None,
    ) -> TrackedContract:
        """
        Register a new contract for indexing.

        Args:
            contract_id: Stellar contract address (C...)
            name: Human-readable name
            description: Optional description
            abi_schema: Optional ABI/schema for decoding

        Returns:
            Created contract
        """
        url = urljoin(self.base_url, "/api/contracts/")
        payload: dict[str, Any] = {
            "contract_id": contract_id,
            "name": name,
            "description": description,
        }
        if abi_schema:
            payload["abi_schema"] = abi_schema

        response = self._client.post(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return TrackedContract.model_validate(data)

    def update_contract(
        self,
        contract_id: str,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> TrackedContract:
        """
        Update a tracked contract.

        Args:
            contract_id: Contract database ID
            name: New name
            description: New description
            is_active: Active status

        Returns:
            Updated contract
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/")
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if is_active is not None:
            payload["is_active"] = is_active

        response = self._client.patch(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return TrackedContract.model_validate(data)

    def delete_contract(self, contract_id: str) -> None:
        """
        Delete a tracked contract.

        Args:
            contract_id: Contract database ID
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/")
        response = self._client.delete(url, headers=self._get_headers())
        if response.status_code != 204:
            self._handle_response(response)

    def get_contract_stats(self, contract_id: str) -> ContractStats:
        """
        Get aggregate statistics for a contract.

        Args:
            contract_id: Contract database ID

        Returns:
            Contract statistics
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/stats/")
        response = self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return ContractStats.model_validate(data)

    def get_events(
        self,
        contract_id: str | None = None,
        event_type: str | None = None,
        ledger: int | None = None,
        ledger_min: int | None = None,
        ledger_max: int | None = None,
        validation_status: Literal["passed", "failed"] | None = None,
        ordering: str = "-timestamp",
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[ContractEvent]:
        """
        Query indexed events with flexible filtering.

        Args:
            contract_id: Filter by contract address
            event_type: Filter by event type
            ledger: Filter by specific ledger
            ledger_min: Filter events from this ledger onwards
            ledger_max: Filter events up to this ledger
            validation_status: Filter by validation status
            ordering: Sort order (prefix with - for descending)
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated list of events
        """
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "ordering": ordering,
        }
        if contract_id:
            params["contract__contract_id"] = contract_id
        if event_type:
            params["event_type"] = event_type
        if ledger is not None:
            params["ledger"] = ledger
        if ledger_min is not None:
            params["ledger__gte"] = ledger_min
        if ledger_max is not None:
            params["ledger__lte"] = ledger_max
        if validation_status:
            params["validation_status"] = validation_status

        url = urljoin(self.base_url, "/api/events/")
        response = self._client.get(url, headers=self._get_headers(), params=params)
        data = self._handle_response(response)

        adapter = TypeAdapter(PaginatedResponse[ContractEvent])
        return adapter.validate_python(data)

    def get_event(self, event_id: int) -> ContractEvent:
        """
        Get a specific event by ID.

        Args:
            event_id: Event database ID

        Returns:
            Event details
        """
        url = urljoin(self.base_url, f"/api/events/{event_id}/")
        response = self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return ContractEvent.model_validate(data)

    def record_event(
        self,
        contract_id: str,
        event_type: str,
        payload_hash: str,
    ) -> RecordEventResponse:
        """
        Record a new event by submitting to the SoroScan contract.

        Args:
            contract_id: Target contract address
            event_type: Event type name
            payload_hash: SHA-256 hash of payload (hex)

        Returns:
            Submission result
        """
        url = urljoin(self.base_url, "/api/record-event/")
        request = RecordEventRequest(
            contract_id=contract_id,
            event_type=event_type,
            payload_hash=payload_hash,
        )
        response = self._client.post(url, headers=self._get_headers(), json=request.model_dump())
        data = self._handle_response(response)
        return RecordEventResponse.model_validate(data)

    def get_webhooks(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[WebhookSubscription]:
        """
        List webhook subscriptions.

        Args:
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated list of webhooks
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        url = urljoin(self.base_url, "/api/webhooks/")
        response = self._client.get(url, headers=self._get_headers(), params=params)
        data = self._handle_response(response)

        adapter = TypeAdapter(PaginatedResponse[WebhookSubscription])
        return adapter.validate_python(data)

    def get_webhook(self, webhook_id: int) -> WebhookSubscription:
        """
        Get a specific webhook by ID.

        Args:
            webhook_id: Webhook database ID

        Returns:
            Webhook details
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/")
        response = self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return WebhookSubscription.model_validate(data)

    def create_webhook(
        self,
        contract_id: int,
        target_url: str,
        event_type: str = "",
    ) -> WebhookSubscription:
        """
        Create a new webhook subscription.

        Args:
            contract_id: Contract database ID to monitor
            target_url: URL to POST event data to
            event_type: Event type filter (empty = all events)

        Returns:
            Created webhook
        """
        url = urljoin(self.base_url, "/api/webhooks/")
        payload = {
            "contract": contract_id,
            "target_url": target_url,
            "event_type": event_type,
        }
        response = self._client.post(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return WebhookSubscription.model_validate(data)

    def update_webhook(
        self,
        webhook_id: int,
        target_url: str | None = None,
        event_type: str | None = None,
        is_active: bool | None = None,
    ) -> WebhookSubscription:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook database ID
            target_url: New target URL
            event_type: New event type filter
            is_active: Active status

        Returns:
            Updated webhook
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/")
        payload: dict[str, Any] = {}
        if target_url is not None:
            payload["target_url"] = target_url
        if event_type is not None:
            payload["event_type"] = event_type
        if is_active is not None:
            payload["is_active"] = is_active

        response = self._client.patch(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return WebhookSubscription.model_validate(data)

    def delete_webhook(self, webhook_id: int) -> None:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: Webhook database ID
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/")
        response = self._client.delete(url, headers=self._get_headers())
        if response.status_code != 204:
            self._handle_response(response)

    def test_webhook(self, webhook_id: int) -> dict[str, Any]:
        """
        Send a test webhook.

        Args:
            webhook_id: Webhook database ID

        Returns:
            Test result
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/test/")
        response = self._client.post(url, headers=self._get_headers())
        return self._handle_response(response)


class AsyncSoroScanClient:
    """
    Asynchronous client for the SoroScan API.

    Example:
        >>> async with AsyncSoroScanClient(base_url="https://api.soroscan.io") as client:
        ...     events = await client.get_events(contract_id="CCAAA...", first=50)
    """

    def __init__(
        self,
        base_url: str = "https://api.soroscan.io",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the async SoroScan client.

        Args:
            base_url: Base URL of the SoroScan API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "AsyncSoroScanClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def _get_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response and raise appropriate exceptions."""
        if response.status_code == 200 or response.status_code == 201:
            return response.json()  # type: ignore[no-any-return]
        elif response.status_code == 202:
            return response.json()  # type: ignore[no-any-return]

        try:
            error_data = response.json()
        except Exception:
            error_data = {}

        error_message = error_data.get("detail") or error_data.get("error") or response.text

        if response.status_code == 400:
            raise SoroScanValidationError(error_message, response.status_code, error_data)
        elif response.status_code == 401 or response.status_code == 403:
            raise SoroScanAuthError(error_message, response.status_code, error_data)
        elif response.status_code == 404:
            raise SoroScanNotFoundError(error_message, response.status_code, error_data)
        elif response.status_code == 429:
            raise SoroScanRateLimitError(error_message, response.status_code, error_data)
        else:
            raise SoroScanAPIError(error_message, response.status_code, error_data)

    async def get_contracts(
        self,
        is_active: bool | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[TrackedContract]:
        """
        List tracked contracts.

        Args:
            is_active: Filter by active status
            search: Search by name or contract_id
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated list of tracked contracts
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if is_active is not None:
            params["is_active"] = is_active
        if search:
            params["search"] = search

        url = urljoin(self.base_url, "/api/contracts/")
        response = await self._client.get(url, headers=self._get_headers(), params=params)
        data = self._handle_response(response)

        adapter = TypeAdapter(PaginatedResponse[TrackedContract])
        return adapter.validate_python(data)

    async def get_contract(self, contract_id: str) -> TrackedContract:
        """
        Get a specific contract by ID.

        Args:
            contract_id: Contract database ID or contract address

        Returns:
            Contract details
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/")
        response = await self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return TrackedContract.model_validate(data)

    async def create_contract(
        self,
        contract_id: str,
        name: str,
        description: str = "",
        abi_schema: dict[str, Any] | None = None,
    ) -> TrackedContract:
        """
        Register a new contract for indexing.

        Args:
            contract_id: Stellar contract address (C...)
            name: Human-readable name
            description: Optional description
            abi_schema: Optional ABI/schema for decoding

        Returns:
            Created contract
        """
        url = urljoin(self.base_url, "/api/contracts/")
        payload: dict[str, Any] = {
            "contract_id": contract_id,
            "name": name,
            "description": description,
        }
        if abi_schema:
            payload["abi_schema"] = abi_schema

        response = await self._client.post(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return TrackedContract.model_validate(data)

    async def update_contract(
        self,
        contract_id: str,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> TrackedContract:
        """
        Update a tracked contract.

        Args:
            contract_id: Contract database ID
            name: New name
            description: New description
            is_active: Active status

        Returns:
            Updated contract
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/")
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if is_active is not None:
            payload["is_active"] = is_active

        response = await self._client.patch(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return TrackedContract.model_validate(data)

    async def delete_contract(self, contract_id: str) -> None:
        """
        Delete a tracked contract.

        Args:
            contract_id: Contract database ID
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/")
        response = await self._client.delete(url, headers=self._get_headers())
        if response.status_code != 204:
            self._handle_response(response)

    async def get_contract_stats(self, contract_id: str) -> ContractStats:
        """
        Get aggregate statistics for a contract.

        Args:
            contract_id: Contract database ID

        Returns:
            Contract statistics
        """
        url = urljoin(self.base_url, f"/api/contracts/{contract_id}/stats/")
        response = await self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return ContractStats.model_validate(data)

    async def get_events(
        self,
        contract_id: str | None = None,
        event_type: str | None = None,
        ledger: int | None = None,
        ledger_min: int | None = None,
        ledger_max: int | None = None,
        validation_status: Literal["passed", "failed"] | None = None,
        ordering: str = "-timestamp",
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[ContractEvent]:
        """
        Query indexed events with flexible filtering.

        Args:
            contract_id: Filter by contract address
            event_type: Filter by event type
            ledger: Filter by specific ledger
            ledger_min: Filter events from this ledger onwards
            ledger_max: Filter events up to this ledger
            validation_status: Filter by validation status
            ordering: Sort order (prefix with - for descending)
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated list of events
        """
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "ordering": ordering,
        }
        if contract_id:
            params["contract__contract_id"] = contract_id
        if event_type:
            params["event_type"] = event_type
        if ledger is not None:
            params["ledger"] = ledger
        if ledger_min is not None:
            params["ledger__gte"] = ledger_min
        if ledger_max is not None:
            params["ledger__lte"] = ledger_max
        if validation_status:
            params["validation_status"] = validation_status

        url = urljoin(self.base_url, "/api/events/")
        response = await self._client.get(url, headers=self._get_headers(), params=params)
        data = self._handle_response(response)

        adapter = TypeAdapter(PaginatedResponse[ContractEvent])
        return adapter.validate_python(data)

    async def get_event(self, event_id: int) -> ContractEvent:
        """
        Get a specific event by ID.

        Args:
            event_id: Event database ID

        Returns:
            Event details
        """
        url = urljoin(self.base_url, f"/api/events/{event_id}/")
        response = await self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return ContractEvent.model_validate(data)

    async def record_event(
        self,
        contract_id: str,
        event_type: str,
        payload_hash: str,
    ) -> RecordEventResponse:
        """
        Record a new event by submitting to the SoroScan contract.

        Args:
            contract_id: Target contract address
            event_type: Event type name
            payload_hash: SHA-256 hash of payload (hex)

        Returns:
            Submission result
        """
        url = urljoin(self.base_url, "/api/record-event/")
        request = RecordEventRequest(
            contract_id=contract_id,
            event_type=event_type,
            payload_hash=payload_hash,
        )
        response = await self._client.post(
            url, headers=self._get_headers(), json=request.model_dump()
        )
        data = self._handle_response(response)
        return RecordEventResponse.model_validate(data)

    async def get_webhooks(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[WebhookSubscription]:
        """
        List webhook subscriptions.

        Args:
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated list of webhooks
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        url = urljoin(self.base_url, "/api/webhooks/")
        response = await self._client.get(url, headers=self._get_headers(), params=params)
        data = self._handle_response(response)

        adapter = TypeAdapter(PaginatedResponse[WebhookSubscription])
        return adapter.validate_python(data)

    async def get_webhook(self, webhook_id: int) -> WebhookSubscription:
        """
        Get a specific webhook by ID.

        Args:
            webhook_id: Webhook database ID

        Returns:
            Webhook details
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/")
        response = await self._client.get(url, headers=self._get_headers())
        data = self._handle_response(response)
        return WebhookSubscription.model_validate(data)

    async def create_webhook(
        self,
        contract_id: int,
        target_url: str,
        event_type: str = "",
    ) -> WebhookSubscription:
        """
        Create a new webhook subscription.

        Args:
            contract_id: Contract database ID to monitor
            target_url: URL to POST event data to
            event_type: Event type filter (empty = all events)

        Returns:
            Created webhook
        """
        url = urljoin(self.base_url, "/api/webhooks/")
        payload = {
            "contract": contract_id,
            "target_url": target_url,
            "event_type": event_type,
        }
        response = await self._client.post(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return WebhookSubscription.model_validate(data)

    async def update_webhook(
        self,
        webhook_id: int,
        target_url: str | None = None,
        event_type: str | None = None,
        is_active: bool | None = None,
    ) -> WebhookSubscription:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook database ID
            target_url: New target URL
            event_type: New event type filter
            is_active: Active status

        Returns:
            Updated webhook
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/")
        payload: dict[str, Any] = {}
        if target_url is not None:
            payload["target_url"] = target_url
        if event_type is not None:
            payload["event_type"] = event_type
        if is_active is not None:
            payload["is_active"] = is_active

        response = await self._client.patch(url, headers=self._get_headers(), json=payload)
        data = self._handle_response(response)
        return WebhookSubscription.model_validate(data)

    async def delete_webhook(self, webhook_id: int) -> None:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: Webhook database ID
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/")
        response = await self._client.delete(url, headers=self._get_headers())
        if response.status_code != 204:
            self._handle_response(response)

    async def test_webhook(self, webhook_id: int) -> dict[str, Any]:
        """
        Send a test webhook.

        Args:
            webhook_id: Webhook database ID

        Returns:
            Test result
        """
        url = urljoin(self.base_url, f"/api/webhooks/{webhook_id}/test/")
        response = await self._client.post(url, headers=self._get_headers())
        return self._handle_response(response)
