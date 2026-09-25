// ─────────────────────────────────────────────────────────────────────────────
// Client configuration
// ─────────────────────────────────────────────────────────────────────────────

export interface SoroScanClientConfig {
  /** Base URL of the SoroScan API, e.g. "https://api.soroscan.io" */
  baseUrl: string;
  /** Optional API key sent as Bearer token */
  apiKey?: string;
  /** Request timeout in milliseconds (default: 30_000) */
  timeoutMs?: number;
  /** Maximum retry attempts after the initial request (default: 3) */
  maxRetries?: number;
  /** Initial full-jitter backoff ceiling in milliseconds (default: 250) */
  initialDelayMs?: number;
  /** Maximum full-jitter backoff ceiling in milliseconds (default: 10_000) */
  maxDelayMs?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared / primitive types
// ─────────────────────────────────────────────────────────────────────────────

/** ISO-8601 date-time string */
export type ISODateString = string;

/** Stellar contract address (C…) */
export type ContractId = string;

/** Stellar account address (G…) or contract address (C…) */
export type StellarAddress = string;

export type Network = "mainnet" | "testnet" | "futurenet";

export type LedgerEntryType =
  | "contract_data"
  | "contract_code"
  | "account"
  | "trustline"
  | "offer"
  | "data"
  | "claimable_balance"
  | "liquidity_pool";

// ─────────────────────────────────────────────────────────────────────────────
// Pagination
// ─────────────────────────────────────────────────────────────────────────────

export interface PageInfo {
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  startCursor: string | null;
  endCursor: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  pageInfo: PageInfo;
  totalCount: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Events
// ─────────────────────────────────────────────────────────────────────────────

export type EventType =
  | "transfer"
  | "mint"
  | "burn"
  | "approve"
  | "clawback"
  | "set_admin"
  | "set_authorized"
  | string; // allow custom event types

export interface ContractEventTopic {
  type: string;
  value: string;
}

export interface ContractEvent<T = unknown> {
  id: string;
  ledger: number;
  ledgerClosedAt: ISODateString;
  txHash: string;
  contractId: ContractId;
  type: EventType;
  topics: ContractEventTopic[];
  value: T;
  inSuccessfulContractCall: boolean;
  pagingToken: string;
}

export interface GetEventsParams {
  /** Filter by contract address */
  contractId?: ContractId;
  /** Filter by event type (e.g. "transfer") */
  eventType?: EventType;
  /** Filter events at or after this ledger */
  startLedger?: number;
  /** Filter events at or before this ledger */
  endLedger?: number;
  /** Cursor-based pagination — fetch records after this cursor */
  after?: string;
  /** Cursor-based pagination — fetch records before this cursor */
  before?: string;
  /** Number of records to return (max 200, default 20) */
  first?: number;
  /** Number of records to return from the end (max 200) */
  last?: number;
}

export type GetEventsResponse = PaginatedResponse<ContractEvent>;

/** Query events across up to ten contracts in one request. */
export interface GetEventsByContractsParams {
  contractIds: ContractId[];
  eventType?: EventType;
  startLedger?: number;
  endLedger?: number;
  page?: number;
  pageSize?: number;
}

export interface GetEventsByContractsResponse {
  count: number;
  results: ContractEvent[];
  contractIds: ContractId[];
}

/** SC-38 input for a versioned event. Both hash values are 32-byte hex strings. */
export interface RecordStructuredEventParams {
  contractId: ContractId;
  eventType: EventType;
  payloadHash: string;
  schemaVersion: number;
  correlationId: string;
}

export interface RecordStructuredEventResponse {
  status: "submitted" | "failed";
  txHash?: string;
  transactionStatus: string;
  error?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Contracts
// ─────────────────────────────────────────────────────────────────────────────

export type ContractType = "token" | "nft" | "dex" | "lending" | "custom";

export interface ContractSpec {
  functions: ContractFunction[];
  types: ContractTypeDefinition[];
}

export interface ContractFunction {
  name: string;
  inputs: ContractFunctionParam[];
  outputs: ContractFunctionParam[];
  doc?: string;
}

export interface ContractFunctionParam {
  name: string;
  type: string;
}

export interface ContractTypeDefinition {
  name: string;
  kind: "struct" | "enum" | "union" | "error";
  fields?: ContractFunctionParam[];
}

export interface Contract {
  id: ContractId;
  network: Network;
  type: ContractType;
  wasmHash: string;
  creator: StellarAddress;
  createdAt: ISODateString;
  createdLedger: number;
  lastActivityAt: ISODateString | null;
  totalEvents: number;
  spec: ContractSpec | null;
  verified: boolean;
  verifiedAt: ISODateString | null;
  sourceCode: string | null;
  label: string | null;
}

export interface GetContractsParams {
  /** Filter by contract type */
  type?: ContractType;
  /** Filter by creator address */
  creator?: StellarAddress;
  /** Search label or contract ID (partial match) */
  search?: string;
  /** Show only verified contracts */
  verified?: boolean;
  after?: string;
  before?: string;
  first?: number;
  last?: number;
}

export type GetContractsResponse = PaginatedResponse<Contract>;

export interface GetContractParams {
  contractId: ContractId;
}

// ─────────────────────────────────────────────────────────────────────────────
// Transactions
// ─────────────────────────────────────────────────────────────────────────────

export type TransactionStatus = "success" | "failed" | "pending";

export interface Transaction {
  hash: string;
  ledger: number;
  createdAt: ISODateString;
  sourceAccount: StellarAddress;
  fee: string;
  status: TransactionStatus;
  operationCount: number;
  envelopeXdr: string;
  resultXdr: string;
  metaXdr: string;
  contractIds: ContractId[];
}

export interface GetTransactionsParams {
  contractId?: ContractId;
  account?: StellarAddress;
  status?: TransactionStatus;
  after?: string;
  before?: string;
  first?: number;
  last?: number;
}

export type GetTransactionsResponse = PaginatedResponse<Transaction>;

// ─────────────────────────────────────────────────────────────────────────────
// Ledgers
// ─────────────────────────────────────────────────────────────────────────────

export interface Ledger {
  sequence: number;
  hash: string;
  closedAt: ISODateString;
  transactionCount: number;
  operationCount: number;
  totalFees: string;
  baseFee: number;
  baseReserve: number;
}

/**
 * SC-38: Input for submitting a structured, deduplicated event.
 * The `correlationId` must be unique per event; duplicate submissions are
 * rejected by the contract so callers can safely retry on network error.
 */
export interface RecordStructuredEventParams {
  contractId: ContractId;
  eventType: EventType;
  payloadHash: string;
  /** Must be > 0. Used by the contract to select the correct decoder. */
  schemaVersion: number;
  /** 32-byte hex correlation id for idempotent submission. */
  correlationId: string;
}

export interface RecordStructuredEventResponse {
  status: "submitted" | "failed";
  txHash?: string;
  transactionStatus: string;
  error?: string;
}

/** Maximum number of producer-defined tags per SC-24 event. */
export const MAX_TAGS = 4;

/**
 * SC-24 input for a tagged event. Tags are short producer-defined
 * classification strings (e.g. ["defi", "token"]) that allow off-chain
 * indexers to filter events without decoding the full payload.
 * At most {@link MAX_TAGS} tags may be supplied.
 */
export interface RecordTaggedEventParams {
  contractId: ContractId;
  eventType: EventType;
  payloadHash: string;
  /** Up to {@link MAX_TAGS} producer-defined classification tags. */
  tags?: string[];
}

export interface RecordTaggedEventResponse {
  status: "submitted" | "failed";
  txHash?: string;
  transactionStatus: string;
  error?: string;
  /** Echo of the tags that were submitted with the event. */
  tags: string[];
}

export interface GetLedgersParams {
  after?: string;
  before?: string;
  first?: number;
  last?: number;
}

export type GetLedgersResponse = PaginatedResponse<Ledger>;

// ─────────────────────────────────────────────────────────────────────────────
// Accounts
// ─────────────────────────────────────────────────────────────────────────────

export interface AccountBalance {
  assetType: "native" | "credit_alphanum4" | "credit_alphanum12";
  assetCode?: string;
  assetIssuer?: string;
  balance: string;
}

export interface Account {
  id: StellarAddress;
  sequence: string;
  balances: AccountBalance[];
  subentryCount: number;
  inflationDest: StellarAddress | null;
  homeDomain: string | null;
  lastModifiedLedger: number;
  lastModifiedAt: ISODateString;
  contractInteractions: number;
}

export interface GetAccountParams {
  accountId: StellarAddress;
}

// ─────────────────────────────────────────────────────────────────────────────
// Webhooks
// ─────────────────────────────────────────────────────────────────────────────

export type WebhookTrigger =
  | "event.created"
  | "contract.deployed"
  | "transaction.success"
  | "transaction.failed";

export type WebhookStatus = "active" | "paused" | "failed";

export interface Webhook {
  id: string;
  url: string;
  triggers: WebhookTrigger[];
  contractId: ContractId | null;
  status: WebhookStatus;
  secret: string;
  createdAt: ISODateString;
  lastDeliveredAt: ISODateString | null;
  failureCount: number;
}

export interface SubscribeWebhookParams {
  /** HTTPS endpoint that will receive POST notifications */
  url: string;
  /** One or more event triggers to subscribe to */
  triggers: WebhookTrigger[];
  /** Optionally scope notifications to a single contract */
  contractId?: ContractId;
  /** Shared secret used to sign webhook payloads (HMAC-SHA256) */
  secret?: string;
}

export interface UpdateWebhookParams {
  url?: string;
  triggers?: WebhookTrigger[];
  status?: "active" | "paused";
}

export interface WebhookListResponse {
  items: Webhook[];
  totalCount: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// SC-16: Contract health
// ─────────────────────────────────────────────────────────────────────────────

export interface ContractHealth {
  /** Contract address */
  contractId: string;
  /** Health status (healthy/unhealthy) */
  status: string;
  /** Timestamp of last event */
  lastEventTime: string | null;
  /** Minutes since last event */
  minutesSinceLastEvent: number | null;
  /** ABI decode errors in last hour */
  abiDecodeErrors1h: number;
  /** Consecutive indexing failures */
  consecutiveFailures: number;
  /** Error message if unhealthy */
  errorMessage: string;
  /** When health was last checked */
  checkedAt: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// SC-29: Batch event recording
// ─────────────────────────────────────────────────────────────────────────────

export interface EventEntry {
  /** Target contract address */
  contractId: ContractId;
  /** Event type name (e.g. "transfer", "swap") */
  eventType: EventType;
  /** SHA-256 hash of the event payload (hex) */
  payloadHash: string;
}

export interface RecordEventsBatchParams {
  /** 1–25 event entries to record in a single transaction */
  events: EventEntry[];
}

export interface RecordEventsBatchResponse {
  status: string;
  /** New total event count after the batch */
  totalEvents: number;
  txHash: string | null;
  transactionStatus: string | null;
  error: string | null;
}

export interface GetAdminResponse {
  admin_address: string | null;
}

export interface IsIndexerResponse {
  is_indexer: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// SC-9: Indexer authorization
// ─────────────────────────────────────────────────────────────────────────────

export interface AddIndexerParams {
  /** Stellar address of the indexer to authorize */
  indexerAddress: StellarAddress;
}

export interface AddIndexerResponse {
  status: string;
  txHash: string | null;
  transactionStatus: string | null;
  error: string | null;
// SC-30: Recent contract events
// ─────────────────────────────────────────────────────────────────────────────

/** Maximum number of events that can be requested via `getContractRecentEvents`. */
export const MAX_RECENT_EVENTS_LIMIT = 20;

export interface GetContractRecentEventsParams {
  /** Contract address to fetch recent events for */
  contractId: ContractId;
  /** Maximum number of events to return (1-20, default 10) */
  limit?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────────────────────────────────────

export interface WebSocketClientConfig {
  /** Base URL of the SoroScan WebSocket server (e.g., "wss://api.soroscan.io") */
  wsUrl: string;

  /** Optional API key for authentication */
  apiKey?: string;

  /** Initial reconnection delay in milliseconds (default: 1000) */
  initialReconnectDelay?: number;

  /** Maximum reconnection delay in milliseconds (default: 30000) */
  maxReconnectDelay?: number;

  /** Backoff multiplier for exponential backoff (default: 2) */
  backoffMultiplier?: number;

  /** Whether to add jitter to reconnection delays (default: true) */
  useJitter?: boolean;

  /** Maximum messages to buffer while disconnected (default: 1000) */
  maxBufferSize?: number;
}

export type EventCallback = (event: ContractEvent) => void;
export type ConnectionCallback = () => void;
export type ErrorCallback = (error: Error) => void;
export type ReconnectingCallback = (attempt: number, delay: number) => void;

export interface EventFilter {
  /** Filter by contract ID */
  contractId?: string;

  /** Filter by event type */
  eventType?: EventType;

  /** Filter by topics */
  topics?: Partial<ContractEventTopic>[];
}

// ─────────────────────────────────────────────────────────────────────────────
// SC-13: Per-indexer event statistics
// ─────────────────────────────────────────────────────────────────────────────

export interface IndexerStats {
  /** The indexer's Stellar address */
  indexer: string;
  /** Total events recorded by this indexer */
  eventsRecorded: number;
// SC-28: Contract pause status
// ─────────────────────────────────────────────────────────────────────────────

export interface ContractStatus {
  /** Whether event recording is currently paused */
  paused: boolean;
  /** Current admin address */
  admin: string;
  /** Total events recorded so far */
  totalEvents: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Errors
// ─────────────────────────────────────────────────────────────────────────────

export interface SoroScanApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
