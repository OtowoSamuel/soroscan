import type { SoroScanClientConfig, SoroScanApiError, GetEventsParams, GetEventsResponse, GetContractsParams, GetContractsResponse, GetContractParams, Contract, GetTransactionsParams, GetTransactionsResponse, GetLedgersParams, GetLedgersResponse, GetAccountParams, Account, SubscribeWebhookParams, UpdateWebhookParams, Webhook, WebhookListResponse } from "./types.js";
export declare class SoroScanError extends Error {
    readonly statusCode: number;
    readonly code: string;
    readonly details: Record<string, unknown> | undefined;
    constructor(statusCode: number, apiError: SoroScanApiError);
}
export declare class SoroScanClient {
    #private;
    constructor(config: SoroScanClientConfig);
    /**
     * Retrieve a paginated list of contract events.
     *
     * @example
     * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
     * for (const event of result.items) { console.log(event.type, event.txHash); }
     */
    getEvents(params?: GetEventsParams): Promise<GetEventsResponse>;
    /**
     * Retrieve a paginated list of deployed contracts.
     *
     * @example
     * const result = await client.getContracts({ type: 'token', verified: true });
     */
    getContracts(params?: GetContractsParams): Promise<GetContractsResponse>;
    /**
     * Retrieve details for a single contract by its address.
     *
     * @example
     * const contract = await client.getContract({ contractId: 'CCAAA...' });
     */
    getContract(params: GetContractParams): Promise<Contract>;
    /**
     * Retrieve a paginated list of transactions, optionally filtered by contract
     * or account.
     */
    getTransactions(params?: GetTransactionsParams): Promise<GetTransactionsResponse>;
    /**
     * Retrieve a single transaction by hash.
     */
    getTransaction(txHash: string): Promise<import("./types.js").Transaction>;
    /**
     * Retrieve a paginated list of ledgers.
     */
    getLedgers(params?: GetLedgersParams): Promise<GetLedgersResponse>;
    /**
     * Retrieve a single ledger by sequence number.
     */
    getLedger(sequence: number): Promise<import("./types.js").Ledger>;
    /**
     * Retrieve account details including balances and contract interaction count.
     */
    getAccount(params: GetAccountParams): Promise<Account>;
    /**
     * Create a new webhook subscription.
     *
     * @example
     * const webhook = await client.subscribeWebhook({
     *   url: 'https://myapp.com/webhook',
     *   triggers: ['event.created'],
     *   contractId: 'CCAAA...',
     * });
     * console.log('Webhook secret:', webhook.secret);
     */
    subscribeWebhook(params: SubscribeWebhookParams): Promise<Webhook>;
    /**
     * List all webhook subscriptions for the authenticated API key.
     */
    listWebhooks(): Promise<WebhookListResponse>;
    /**
     * Retrieve a single webhook by ID.
     */
    getWebhook(webhookId: string): Promise<Webhook>;
    /**
     * Update a webhook (URL, triggers, or status).
     */
    updateWebhook(webhookId: string, params: UpdateWebhookParams): Promise<Webhook>;
    /**
     * Delete (unsubscribe) a webhook.
     */
    deleteWebhook(webhookId: string): Promise<void>;
}
