// ─────────────────────────────────────────────────────────────────────────────
// Error class
// ─────────────────────────────────────────────────────────────────────────────
export class SoroScanError extends Error {
    statusCode;
    code;
    details;
    constructor(statusCode, apiError) {
        super(apiError.message);
        this.name = "SoroScanError";
        this.statusCode = statusCode;
        this.code = apiError.code;
        this.details = apiError.details;
    }
}
// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function toQueryString(params) {
    const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null);
    if (entries.length === 0)
        return "";
    return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}
// ─────────────────────────────────────────────────────────────────────────────
// Client
// ─────────────────────────────────────────────────────────────────────────────
export class SoroScanClient {
    #baseUrl;
    #apiKey;
    #timeoutMs;
    constructor(config) {
        if (!config.baseUrl) {
            throw new Error("SoroScanClient: baseUrl is required");
        }
        this.#baseUrl = config.baseUrl.replace(/\/$/, "");
        this.#apiKey = config.apiKey;
        this.#timeoutMs = config.timeoutMs ?? 30_000;
    }
    // ─── Core fetch ────────────────────────────────────────────────────────────
    async #request(method, path, options = {}) {
        const url = this.#baseUrl +
            path +
            (options.query ? toQueryString(options.query) : "");
        const headers = {
            "Content-Type": "application/json",
            Accept: "application/json",
        };
        if (this.#apiKey) {
            headers["Authorization"] = `Bearer ${this.#apiKey}`;
        }
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.#timeoutMs);
        let response;
        try {
            const init = {
                method,
                headers,
                signal: controller.signal,
            };
            if (options.body !== undefined) {
                init.body = JSON.stringify(options.body);
            }
            response = await fetch(url, init);
        }
        catch (err) {
            if (err instanceof Error && err.name === "AbortError") {
                throw new Error(`SoroScanClient: request timed out after ${this.#timeoutMs}ms`);
            }
            throw err;
        }
        finally {
            clearTimeout(timer);
        }
        // 204 No Content
        if (response.status === 204) {
            return undefined;
        }
        const json = await response.json().catch(() => null);
        if (!response.ok) {
            const apiError = json ?? {
                code: "UNKNOWN_ERROR",
                message: `HTTP ${response.status} ${response.statusText}`,
            };
            throw new SoroScanError(response.status, apiError);
        }
        return json;
    }
    // ─── Events ────────────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of contract events.
     *
     * @example
     * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
     * for (const event of result.items) { console.log(event.type, event.txHash); }
     */
    async getEvents(params = {}) {
        return this.#request("GET", "/v1/events", {
            query: params,
        });
    }
    // ─── Contracts ─────────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of deployed contracts.
     *
     * @example
     * const result = await client.getContracts({ type: 'token', verified: true });
     */
    async getContracts(params = {}) {
        return this.#request("GET", "/v1/contracts", {
            query: params,
        });
    }
    /**
     * Retrieve details for a single contract by its address.
     *
     * @example
     * const contract = await client.getContract({ contractId: 'CCAAA...' });
     */
    async getContract(params) {
        const { contractId } = params;
        return this.#request("GET", `/v1/contracts/${encodeURIComponent(contractId)}`);
    }
    // ─── Transactions ──────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of transactions, optionally filtered by contract
     * or account.
     */
    async getTransactions(params = {}) {
        return this.#request("GET", "/v1/transactions", {
            query: params,
        });
    }
    /**
     * Retrieve a single transaction by hash.
     */
    async getTransaction(txHash) {
        return this.#request("GET", `/v1/transactions/${encodeURIComponent(txHash)}`);
    }
    // ─── Ledgers ───────────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of ledgers.
     */
    async getLedgers(params = {}) {
        return this.#request("GET", "/v1/ledgers", {
            query: params,
        });
    }
    /**
     * Retrieve a single ledger by sequence number.
     */
    async getLedger(sequence) {
        return this.#request("GET", `/v1/ledgers/${sequence}`);
    }
    // ─── Accounts ──────────────────────────────────────────────────────────────
    /**
     * Retrieve account details including balances and contract interaction count.
     */
    async getAccount(params) {
        const { accountId } = params;
        return this.#request("GET", `/v1/accounts/${encodeURIComponent(accountId)}`);
    }
    // ─── Webhooks ──────────────────────────────────────────────────────────────
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
    async subscribeWebhook(params) {
        return this.#request("POST", "/v1/webhooks", { body: params });
    }
    /**
     * List all webhook subscriptions for the authenticated API key.
     */
    async listWebhooks() {
        return this.#request("GET", "/v1/webhooks");
    }
    /**
     * Retrieve a single webhook by ID.
     */
    async getWebhook(webhookId) {
        return this.#request("GET", `/v1/webhooks/${encodeURIComponent(webhookId)}`);
    }
    /**
     * Update a webhook (URL, triggers, or status).
     */
    async updateWebhook(webhookId, params) {
        return this.#request("PATCH", `/v1/webhooks/${encodeURIComponent(webhookId)}`, { body: params });
    }
    /**
     * Delete (unsubscribe) a webhook.
     */
    async deleteWebhook(webhookId) {
        return this.#request("DELETE", `/v1/webhooks/${encodeURIComponent(webhookId)}`);
    }
}
//# sourceMappingURL=client.js.map