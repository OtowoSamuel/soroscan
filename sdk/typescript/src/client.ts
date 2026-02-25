import type {
  SoroScanClientConfig,
  SoroScanApiError,
  GetEventsParams,
  GetEventsResponse,
  GetContractsParams,
  GetContractsResponse,
  GetContractParams,
  Contract,
  GetTransactionsParams,
  GetTransactionsResponse,
  GetLedgersParams,
  GetLedgersResponse,
  GetAccountParams,
  Account,
  SubscribeWebhookParams,
  UpdateWebhookParams,
  Webhook,
  WebhookListResponse,
} from "./types.js";

// ─────────────────────────────────────────────────────────────────────────────
// Error class
// ─────────────────────────────────────────────────────────────────────────────

export class SoroScanError extends Error {
  readonly statusCode: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(statusCode: number, apiError: SoroScanApiError) {
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

function toQueryString(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null
  );
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

// ─────────────────────────────────────────────────────────────────────────────
// Client
// ─────────────────────────────────────────────────────────────────────────────

export class SoroScanClient {
  readonly #baseUrl: string;
  readonly #apiKey: string | undefined;
  readonly #timeoutMs: number;

  constructor(config: SoroScanClientConfig) {
    if (!config.baseUrl) {
      throw new Error("SoroScanClient: baseUrl is required");
    }
    this.#baseUrl = config.baseUrl.replace(/\/$/, "");
    this.#apiKey = config.apiKey;
    this.#timeoutMs = config.timeoutMs ?? 30_000;
  }

  // ─── Core fetch ────────────────────────────────────────────────────────────

  async #request<T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path: string,
    options: {
      query?: Record<string, unknown>;
      body?: unknown;
    } = {}
  ): Promise<T> {
    const url =
      this.#baseUrl +
      path +
      (options.query ? toQueryString(options.query) : "");

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (this.#apiKey) {
      headers["Authorization"] = `Bearer ${this.#apiKey}`;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.#timeoutMs);

    let response: Response;
    try {
      const init: RequestInit = {
        method,
        headers,
        signal: controller.signal as RequestInit["signal"],
      };
      if (options.body !== undefined) {
        init.body = JSON.stringify(options.body);
      }
      response = await fetch(url, init);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`SoroScanClient: request timed out after ${this.#timeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }

    // 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    const json = await response.json().catch(() => null);

    if (!response.ok) {
      const apiError: SoroScanApiError = json ?? {
        code: "UNKNOWN_ERROR",
        message: `HTTP ${response.status} ${response.statusText}`,
      };
      throw new SoroScanError(response.status, apiError);
    }

    return json as T;
  }

  // ─── Events ────────────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of contract events.
   *
   * @example
   * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
   * for (const event of result.items) { console.log(event.type, event.txHash); }
   */
  async getEvents(params: GetEventsParams = {}): Promise<GetEventsResponse> {
    return this.#request<GetEventsResponse>("GET", "/v1/events", {
      query: params as Record<string, unknown>,
    });
  }

  // ─── Contracts ─────────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of deployed contracts.
   *
   * @example
   * const result = await client.getContracts({ type: 'token', verified: true });
   */
  async getContracts(
    params: GetContractsParams = {}
  ): Promise<GetContractsResponse> {
    return this.#request<GetContractsResponse>("GET", "/v1/contracts", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve details for a single contract by its address.
   *
   * @example
   * const contract = await client.getContract({ contractId: 'CCAAA...' });
   */
  async getContract(params: GetContractParams): Promise<Contract> {
    const { contractId } = params;
    return this.#request<Contract>(
      "GET",
      `/v1/contracts/${encodeURIComponent(contractId)}`
    );
  }

  // ─── Transactions ──────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of transactions, optionally filtered by contract
   * or account.
   */
  async getTransactions(
    params: GetTransactionsParams = {}
  ): Promise<GetTransactionsResponse> {
    return this.#request<GetTransactionsResponse>("GET", "/v1/transactions", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve a single transaction by hash.
   */
  async getTransaction(
    txHash: string
  ): Promise<import("./types.js").Transaction> {
    return this.#request("GET", `/v1/transactions/${encodeURIComponent(txHash)}`);
  }

  // ─── Ledgers ───────────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of ledgers.
   */
  async getLedgers(params: GetLedgersParams = {}): Promise<GetLedgersResponse> {
    return this.#request<GetLedgersResponse>("GET", "/v1/ledgers", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve a single ledger by sequence number.
   */
  async getLedger(sequence: number): Promise<import("./types.js").Ledger> {
    return this.#request("GET", `/v1/ledgers/${sequence}`);
  }

  // ─── Accounts ──────────────────────────────────────────────────────────────

  /**
   * Retrieve account details including balances and contract interaction count.
   */
  async getAccount(params: GetAccountParams): Promise<Account> {
    const { accountId } = params;
    return this.#request<Account>(
      "GET",
      `/v1/accounts/${encodeURIComponent(accountId)}`
    );
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
  async subscribeWebhook(params: SubscribeWebhookParams): Promise<Webhook> {
    return this.#request<Webhook>("POST", "/v1/webhooks", { body: params });
  }

  /**
   * List all webhook subscriptions for the authenticated API key.
   */
  async listWebhooks(): Promise<WebhookListResponse> {
    return this.#request<WebhookListResponse>("GET", "/v1/webhooks");
  }

  /**
   * Retrieve a single webhook by ID.
   */
  async getWebhook(webhookId: string): Promise<Webhook> {
    return this.#request<Webhook>(
      "GET",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`
    );
  }

  /**
   * Update a webhook (URL, triggers, or status).
   */
  async updateWebhook(
    webhookId: string,
    params: UpdateWebhookParams
  ): Promise<Webhook> {
    return this.#request<Webhook>(
      "PATCH",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`,
      { body: params }
    );
  }

  /**
   * Delete (unsubscribe) a webhook.
   */
  async deleteWebhook(webhookId: string): Promise<void> {
    return this.#request<void>(
      "DELETE",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`
    );
  }
}