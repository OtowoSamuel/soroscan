# @soroscan/sdk

> Official TypeScript/JavaScript client SDK for the [SoroScan](https://soroscan.io) API.

[![npm version](https://img.shields.io/npm/v/@soroscan/sdk.svg)](https://www.npmjs.com/package/@soroscan/sdk)
[![CI](https://github.com/SoroScan/soroscan/actions/workflows/sdk-ts.yml/badge.svg)](https://github.com/SoroScan/soroscan/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

- 🔒 **Strict TypeScript** — full types for every request and response shape
- 📦 **Dual ESM / CJS** build — works in Node.js 18+, Vite, Next.js, and modern browsers
- 🚫 **Zero runtime dependencies** — only uses native `fetch`
- 🪝 **Full API coverage** — events, contracts, transactions, ledgers, accounts, webhooks

---

## Installation

```bash
npm install @soroscan/sdk
# or
yarn add @soroscan/sdk
# or
pnpm add @soroscan/sdk
```

---

## Quick Start

```ts
import { SoroScanClient } from "@soroscan/sdk";

const client = new SoroScanClient({
  baseUrl: "https://api.soroscan.io",
  apiKey: process.env.SOROSCAN_API_KEY, // optional for public endpoints
});

// Fetch the 50 most recent "transfer" events for a contract
const events = await client.getEvents({
  contractId: "CCAAA...",
  eventType: "transfer",
  first: 50,
});

for (const event of events.items) {
  console.log(event.ledger, event.type, event.txHash);
}
```

---

## API Reference

### `new SoroScanClient(config)`

| Option | Type | Required | Description |
|---|---|---|---|
| `baseUrl` | `string` | ✅ | API base URL, e.g. `https://api.soroscan.io` |
| `apiKey` | `string` | — | API key sent as `Authorization: Bearer <key>` |
| `timeoutMs` | `number` | — | Request timeout in ms (default: `30_000`) |

---

### Events

#### `client.getEvents(params?)`

Returns a paginated list of contract events.

```ts
const result = await client.getEvents({
  contractId: "CCAAA...",   // filter by contract
  eventType: "transfer",    // filter by event type
  startLedger: 1_000_000,   // range filter
  endLedger:   1_001_000,
  first: 20,                // page size
  after: result.pageInfo.endCursor, // cursor pagination
});

// result: { items: ContractEvent[], pageInfo: PageInfo, totalCount: number }
```

**`GetEventsParams`**

| Field | Type | Description |
|---|---|---|
| `contractId` | `string` | Filter by contract address |
| `eventType` | `string` | e.g. `"transfer"`, `"mint"`, `"burn"` |
| `startLedger` | `number` | Minimum ledger sequence |
| `endLedger` | `number` | Maximum ledger sequence |
| `first` / `last` | `number` | Page size (max 200) |
| `after` / `before` | `string` | Cursor for pagination |

---

### Contracts

#### `client.getContracts(params?)`

Returns a paginated list of deployed contracts.

```ts
const result = await client.getContracts({
  type: "token",
  verified: true,
  first: 10,
});
```

#### `client.getContract({ contractId })`

Returns details for a single contract.

```ts
const contract = await client.getContract({ contractId: "CCAAA..." });
console.log(contract.spec?.functions); // ABI
```

---

### Transactions

#### `client.getTransactions(params?)`

Returns a paginated list of transactions.

```ts
const result = await client.getTransactions({
  contractId: "CCAAA...",
  status: "success",
  first: 25,
});
```

#### `client.getTransaction(txHash)`

Returns a single transaction by hash.

```ts
const tx = await client.getTransaction("abc123...");
```

---

### Ledgers

#### `client.getLedgers(params?)`

Returns a paginated list of ledgers.

```ts
const result = await client.getLedgers({ first: 5 });
```

#### `client.getLedger(sequence)`

Returns a single ledger by sequence number.

```ts
const ledger = await client.getLedger(1_234_567);
```

---

### Accounts

#### `client.getAccount({ accountId })`

Returns account details including balances.

```ts
const account = await client.getAccount({ accountId: "GABC..." });
console.log(account.balances);
```

---

### Webhooks

#### `client.subscribeWebhook(params)`

Creates a new webhook subscription. The returned `secret` is used to verify
incoming payloads via `HMAC-SHA256`.

```ts
const webhook = await client.subscribeWebhook({
  url: "https://myapp.com/webhook/soroscan",
  triggers: ["event.created", "transaction.success"],
  contractId: "CCAAA...",          // optional — scope to one contract
  secret: "my-shared-secret",      // optional — auto-generated if omitted
});

console.log("Webhook ID:", webhook.id);
console.log("Signing secret:", webhook.secret);
```

**Available triggers**

| Trigger | Fires when |
|---|---|
| `event.created` | A new contract event is indexed |
| `contract.deployed` | A new contract is deployed |
| `transaction.success` | A transaction succeeds |
| `transaction.failed` | A transaction fails |

#### `client.listWebhooks()`

Returns all webhooks for the authenticated API key.

#### `client.getWebhook(webhookId)`

Returns a single webhook.

#### `client.updateWebhook(webhookId, params)`

Updates a webhook's URL, triggers, or status.

```ts
await client.updateWebhook("wh_001", { status: "paused" });
```

#### `client.deleteWebhook(webhookId)`

Permanently deletes a webhook.

---

## Error Handling

All methods throw a `SoroScanError` on non-2xx responses.

```ts
import { SoroScanClient, SoroScanError } from "@soroscan/sdk";

try {
  const contract = await client.getContract({ contractId: "INVALID" });
} catch (err) {
  if (err instanceof SoroScanError) {
    console.error(`[${err.statusCode}] ${err.code}: ${err.message}`);
    // e.g. [404] NOT_FOUND: Contract not found
  }
}
```

`SoroScanError` properties:

| Property | Type | Description |
|---|---|---|
| `statusCode` | `number` | HTTP status code |
| `code` | `string` | Machine-readable error code from the API |
| `message` | `string` | Human-readable message |
| `details` | `object?` | Optional additional context |

---

## Pagination

All list methods return a `PaginatedResponse<T>` with cursor-based pagination:

```ts
let after: string | null = null;

do {
  const page = await client.getEvents({
    contractId: "CCAAA...",
    first: 100,
    ...(after ? { after } : {}),
  });

  for (const event of page.items) {
    process(event);
  }

  after = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
} while (after);
```

---

## TypeScript Usage

All types are exported from the package root:

```ts
import type {
  ContractEvent,
  Contract,
  Webhook,
  GetEventsParams,
  SoroScanClientConfig,
} from "@soroscan/sdk";
```

---

## Node.js / Browser Compatibility

| Environment | Supported |
|---|---|
| Node.js 18+ | ✅ (native `fetch`) |
| Node.js 16 | ⚠️ requires `node-fetch` polyfill |
| Modern browsers | ✅ |
| React Native | ✅ |

---

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) in the monorepo root.

## License

MIT © SoroScan Contributors