"""
SoroScan Python SDK

Official Python client for the SoroScan API - Stellar/Soroban event indexing.
"""

from soroscan.client import AsyncSoroScanClient, SoroScanClient
from soroscan.builder import (
    EventQueryBuilder,
    AsyncEventQueryBuilder,
    ContractQueryBuilder,
    AsyncContractQueryBuilder,
)
from soroscan.pagination import AsyncPaginator, Paginator
from soroscan.exceptions import (
    SoroScanAPIError,
    SoroScanAuthError,
    SoroScanError,
    SoroScanNotFoundError,
    SoroScanRateLimitError,
    SoroScanValidationError,
)
from soroscan.webhook_verification import verify_webhook_signature
from soroscan.models import (
    ContractEvent,
    ContractStats,
    PaginatedResponse,
    TrackedContract,
    WebhookSubscription,
)

__version__ = "0.1.0"
__all__ = [
    "SoroScanClient",
    "AsyncSoroScanClient",
    "EventQueryBuilder",
    "AsyncEventQueryBuilder",
    "ContractQueryBuilder",
    "AsyncContractQueryBuilder",
    "Paginator",
    "AsyncPaginator",
    "ContractEvent",
    "TrackedContract",
    "WebhookSubscription",
    "ContractStats",
    "PaginatedResponse",
    "SoroScanError",
    "SoroScanAPIError",
    "SoroScanAuthError",
    "SoroScanNotFoundError",
    "SoroScanRateLimitError",
    "SoroScanValidationError",
    "verify_webhook_signature",
]
