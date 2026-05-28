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
from soroscan.exceptions import (
    SoroScanAPIError,
    SoroScanAuthError,
    SoroScanError,
    SoroScanNotFoundError,
    SoroScanRateLimitError,
    SoroScanValidationError,
)
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
]
