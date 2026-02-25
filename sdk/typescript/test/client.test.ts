import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SoroScanClient, SoroScanError } from "../src/client.js";
import type {
  GetEventsResponse,
  GetContractsResponse,
  Contract,
  Webhook,
  WebhookListResponse,
  Account,
  GetTransactionsResponse,
  GetLedgersResponse,
  Ledger,
  Transaction,
} from "../src/types.js";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function mockFetch(body: unknown, status = 200): void {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

function mockFetchEmpty(status = 204): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status }))
  );
}

const BASE_URL = "https://api.soroscan.io";

function makeClient(apiKey?: string) {
  return new SoroScanClient({ baseUrl: BASE_URL, apiKey });
}

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures
// ─────────────────────────────────────────────────────────────────────────────

const mockPageInfo = {
  hasNextPage: false,
  hasPreviousPage: false,
  startCursor: "cursor_start",
  endCursor: "cursor_end",
};

const mockEvent = {
  id: "evt_001",
  ledger: 123456,
  ledgerClosedAt: "2024-01-01T00:00:00Z",
  txHash: "abc123",
  contractId: "CCAAA",
  type: "transfer",
  topics: [{ type: "symbol", value: "transfer" }],
  value: { amount: "100" },
  inSuccessfulContractCall: true,
  pagingToken: "123456-1",
};

const mockContract: Contract = {
  id: "CCAAA",
  network: "mainnet",
  type: "token",
  wasmHash: "deadbeef",
  creator: "GABC",
  createdAt: "2024-01-01T00:00:00Z",
  createdLedger: 100000,
  lastActivityAt: "2024-06-01T00:00:00Z",
  totalEvents: 9999,
  spec: null,
  verified: true,
  verifiedAt: "2024-02-01T00:00:00Z",
  sourceCode: null,
  label: "My Token",
};

const mockWebhook: Webhook = {
  id: "wh_001",
  url: "https://myapp.com/hook",
  triggers: ["event.created"],
  contractId: "CCAAA",
  status: "active",
  secret: "s3cr3t",
  createdAt: "2024-01-01T00:00:00Z",
  lastDeliveredAt: null,
  failureCount: 0,
};

const mockAccount: Account = {
  id: "GABC",
  sequence: "1234567",
  balances: [{ assetType: "native", balance: "100.0000000" }],
  subentryCount: 2,
  inflationDest: null,
  homeDomain: null,
  lastModifiedLedger: 99999,
  lastModifiedAt: "2024-05-01T00:00:00Z",
  contractInteractions: 5,
};

const mockTransaction: Transaction = {
  hash: "txhash_001",
  ledger: 123456,
  createdAt: "2024-01-01T00:00:00Z",
  sourceAccount: "GABC",
  fee: "100",
  status: "success",
  operationCount: 1,
  envelopeXdr: "env_xdr",
  resultXdr: "result_xdr",
  metaXdr: "meta_xdr",
  contractIds: ["CCAAA"],
};

const mockLedger: Ledger = {
  sequence: 123456,
  hash: "ledgerhash",
  closedAt: "2024-01-01T00:00:00Z",
  transactionCount: 42,
  operationCount: 100,
  totalFees: "10000",
  baseFee: 100,
  baseReserve: 5000000,
};

// ─────────────────────────────────────────────────────────────────────────────
// Constructor
// ─────────────────────────────────────────────────────────────────────────────

describe("SoroScanClient constructor", () => {
  it("throws when baseUrl is empty", () => {
    expect(() => new SoroScanClient({ baseUrl: "" })).toThrow(
      "baseUrl is required"
    );
  });

  it("strips trailing slash from baseUrl", () => {
    const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io/" });
    expect(client).toBeInstanceOf(SoroScanClient);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Auth header
// ─────────────────────────────────────────────────────────────────────────────

describe("Authorization header", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends Bearer token when apiKey is provided", async () => {
    const eventsResponse: GetEventsResponse = {
      items: [],
      pageInfo: mockPageInfo,
      totalCount: 0,
    };
    mockFetch(eventsResponse);
    const client = makeClient("my-api-key");
    await client.getEvents();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit
    ];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer my-api-key"
    );
  });

  it("omits Authorization header when no apiKey", async () => {
    mockFetch({ items: [], pageInfo: mockPageInfo, totalCount: 0 });
    const client = makeClient();
    await client.getEvents();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit
    ];
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Events
// ─────────────────────────────────────────────────────────────────────────────

describe("getEvents()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns paginated events", async () => {
    const fixture: GetEventsResponse = {
      items: [mockEvent],
      pageInfo: mockPageInfo,
      totalCount: 1,
    };
    mockFetch(fixture);
    const result = await makeClient().getEvents({
      contractId: "CCAAA",
      eventType: "transfer",
      first: 50,
    });
    expect(result.items).toHaveLength(1);
    expect(result.items[0]?.type).toBe("transfer");
  });

  it("builds correct URL with query params", async () => {
    mockFetch({ items: [], pageInfo: mockPageInfo, totalCount: 0 });
    await makeClient().getEvents({ contractId: "CCAAA", first: 10 });

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain("/v1/events");
    expect(url).toContain("contractId=CCAAA");
    expect(url).toContain("first=10");
  });

  it("handles empty result set", async () => {
    const fixture: GetEventsResponse = {
      items: [],
      pageInfo: { ...mockPageInfo, hasNextPage: false },
      totalCount: 0,
    };
    mockFetch(fixture);
    const result = await makeClient().getEvents();
    expect(result.totalCount).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Contracts
// ─────────────────────────────────────────────────────────────────────────────

describe("getContracts()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns paginated contracts", async () => {
    const fixture: GetContractsResponse = {
      items: [mockContract],
      pageInfo: mockPageInfo,
      totalCount: 1,
    };
    mockFetch(fixture);
    const result = await makeClient().getContracts({ type: "token" });
    expect(result.items[0]?.id).toBe("CCAAA");
  });
});

describe("getContract()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetches a single contract", async () => {
    mockFetch(mockContract);
    const result = await makeClient().getContract({ contractId: "CCAAA" });
    expect(result.wasmHash).toBe("deadbeef");
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain("/v1/contracts/CCAAA");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Transactions
// ─────────────────────────────────────────────────────────────────────────────

describe("getTransactions()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns paginated transactions", async () => {
    const fixture: GetTransactionsResponse = {
      items: [mockTransaction],
      pageInfo: mockPageInfo,
      totalCount: 1,
    };
    mockFetch(fixture);
    const result = await makeClient().getTransactions({ contractId: "CCAAA" });
    expect(result.items[0]?.hash).toBe("txhash_001");
  });
});

describe("getTransaction()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetches a single transaction by hash", async () => {
    mockFetch(mockTransaction);
    const result = await makeClient().getTransaction("txhash_001");
    expect(result.status).toBe("success");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Ledgers
// ─────────────────────────────────────────────────────────────────────────────

describe("getLedgers()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns paginated ledgers", async () => {
    const fixture: GetLedgersResponse = {
      items: [mockLedger],
      pageInfo: mockPageInfo,
      totalCount: 1,
    };
    mockFetch(fixture);
    const result = await makeClient().getLedgers({ first: 5 });
    expect(result.items[0]?.sequence).toBe(123456);
  });
});

describe("getLedger()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetches a ledger by sequence", async () => {
    mockFetch(mockLedger);
    const result = await makeClient().getLedger(123456);
    expect(result.transactionCount).toBe(42);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain("/v1/ledgers/123456");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Accounts
// ─────────────────────────────────────────────────────────────────────────────

describe("getAccount()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns account details", async () => {
    mockFetch(mockAccount);
    const result = await makeClient().getAccount({ accountId: "GABC" });
    expect(result.balances).toHaveLength(1);
    expect(result.contractInteractions).toBe(5);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Webhooks
// ─────────────────────────────────────────────────────────────────────────────

describe("subscribeWebhook()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a webhook and returns it", async () => {
    mockFetch(mockWebhook, 201);
    const result = await makeClient("key").subscribeWebhook({
      url: "https://myapp.com/hook",
      triggers: ["event.created"],
      contractId: "CCAAA",
    });
    expect(result.id).toBe("wh_001");
    expect(result.secret).toBe("s3cr3t");

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit
    ];
    expect(url).toContain("/v1/webhooks");
    expect(init.method).toBe("POST");
  });
});

describe("listWebhooks()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns list of webhooks", async () => {
    const fixture: WebhookListResponse = { items: [mockWebhook], totalCount: 1 };
    mockFetch(fixture);
    const result = await makeClient("key").listWebhooks();
    expect(result.items).toHaveLength(1);
  });
});

describe("updateWebhook()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends PATCH request", async () => {
    mockFetch({ ...mockWebhook, status: "paused" });
    const result = await makeClient("key").updateWebhook("wh_001", {
      status: "paused",
    });
    expect(result.status).toBe("paused");

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit
    ];
    expect(init.method).toBe("PATCH");
  });
});

describe("deleteWebhook()", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends DELETE request and returns void", async () => {
    mockFetchEmpty(204);
    const result = await makeClient("key").deleteWebhook("wh_001");
    expect(result).toBeUndefined();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit
    ];
    expect(init.method).toBe("DELETE");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Error handling
// ─────────────────────────────────────────────────────────────────────────────

describe("Error handling", () => {
  afterEach(() => vi.restoreAllMocks());

  it("throws SoroScanError on 404", async () => {
    mockFetch({ code: "NOT_FOUND", message: "Contract not found" }, 404);
    await expect(
      makeClient().getContract({ contractId: "CBAD" })
    ).rejects.toMatchObject({
      name: "SoroScanError",
      statusCode: 404,
      code: "NOT_FOUND",
      message: "Contract not found",
    });
  });

  it("throws SoroScanError on 401", async () => {
    mockFetch({ code: "UNAUTHORIZED", message: "Invalid API key" }, 401);
    await expect(makeClient("bad-key").listWebhooks()).rejects.toMatchObject({
      statusCode: 401,
      code: "UNAUTHORIZED",
    });
  });

  it("throws SoroScanError on 500 with fallback message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("Internal Server Error", {
          status: 500,
          headers: { "Content-Type": "text/plain" },
        })
      )
    );
    await expect(makeClient().getEvents()).rejects.toMatchObject({
      statusCode: 500,
    });
  });

  it("throws on fetch network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))
    );
    await expect(makeClient().getEvents()).rejects.toThrow("Failed to fetch");
  });
});