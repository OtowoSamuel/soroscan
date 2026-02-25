export interface SoroScanClientConfig {
    /** Base URL of the SoroScan API, e.g. "https://api.soroscan.io" */
    baseUrl: string;
    /** Optional API key sent as Bearer token */
    apiKey?: string;
    /** Request timeout in milliseconds (default: 30_000) */
    timeoutMs?: number;
}
/** ISO-8601 date-time string */
export type ISODateString = string;
/** Stellar contract address (C…) */
export type ContractId = string;
/** Stellar account address (G…) or contract address (C…) */
export type StellarAddress = string;
export type Network = "mainnet" | "testnet" | "futurenet";
export type LedgerEntryType = "contract_data" | "contract_code" | "account" | "trustline" | "offer" | "data" | "claimable_balance" | "liquidity_pool";
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
export type EventType = "transfer" | "mint" | "burn" | "approve" | "clawback" | "set_admin" | "set_authorized" | string;
export interface ContractEventTopic {
    type: string;
    value: string;
}
export interface ContractEvent {
    id: string;
    ledger: number;
    ledgerClosedAt: ISODateString;
    txHash: string;
    contractId: ContractId;
    type: EventType;
    topics: ContractEventTopic[];
    value: unknown;
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
export interface GetLedgersParams {
    after?: string;
    before?: string;
    first?: number;
    last?: number;
}
export type GetLedgersResponse = PaginatedResponse<Ledger>;
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
export type WebhookTrigger = "event.created" | "contract.deployed" | "transaction.success" | "transaction.failed";
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
export interface SoroScanApiError {
    code: string;
    message: string;
    details?: Record<string, unknown>;
}
