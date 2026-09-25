/**
 * Fluent query builder pattern for the SoroScan TypeScript SDK (SC-10).
 *
 * Mirrors the Python SDK's builder.py API so developers get a consistent
 * experience across both languages.
 *
 * @example
 * const events = await client
 *   .events()
 *   .filterByContract("CCAAA...")
 *   .filterByEventType("transfer")
 *   .filterByLedgerRange(1_000, 2_000)
 *   .orderBy("-timestamp")
 *   .paginate(50, 0)
 *   .execute();
 */

import type {
  SoroScanClient,
  GetEventsParams,
  GetEventsResponse,
  GetContractsParams,
  GetContractsResponse,
  ContractEvent,
} from "./index.js";
import type { ZodType } from "zod";

// ─────────────────────────────────────────────────────────────────────────────
// EventQueryBuilder
// ─────────────────────────────────────────────────────────────────────────────

export class EventQueryBuilder {
  readonly #client: SoroScanClient;
  #contractId?: string;
  #eventType?: string;
  #startLedger?: number;
  #endLedger?: number;
  #after?: string;
  #before?: string;
  #first: number = 50;
  #last?: number;

  constructor(client: SoroScanClient) {
    this.#client = client;
  }

  /** Filter by contract address. */
  filterByContract(contractId: string): this {
    this.#contractId = contractId;
    return this;
  }

  /** Filter by event type (e.g. "transfer", "swap"). */
  filterByEventType(eventType: string): this {
    this.#eventType = eventType;
    return this;
  }

  /** Filter events at or after this ledger sequence. */
  filterByStartLedger(ledger: number): this {
    this.#startLedger = ledger;
    return this;
  }

  /** Filter events at or before this ledger sequence. */
  filterByEndLedger(ledger: number): this {
    this.#endLedger = ledger;
    return this;
  }

  /**
   * Filter events within an inclusive ledger range.
   * Convenience wrapper for filterByStartLedger + filterByEndLedger.
   */
  filterByLedgerRange(start?: number, end?: number): this {
    if (start !== undefined) this.#startLedger = start;
    if (end !== undefined) this.#endLedger = end;
    return this;
  }

  /**
   * Set cursor for forward pagination.
   * Mutually exclusive with before().
   */
  after(cursor: string): this {
    this.#after = cursor;
    this.#before = undefined;
    return this;
  }

  /**
   * Set cursor for backward pagination.
   * Mutually exclusive with after().
   */
  before(cursor: string): this {
    this.#before = cursor;
    this.#after = undefined;
    return this;
  }

  /**
   * Set page size (number of results to return).
   * Equivalent to calling first(limit).
   *
   * @param limit - max records to return (default 50)
   * @param offset - ignored for cursor pagination; provided for API parity with Python SDK
   */
  paginate(limit: number = 50, _offset?: number): this {
    this.#first = limit;
    return this;
  }

  /** Alias for paginate() — sets how many records to return. */
  first(n: number): this {
    this.#first = n;
    this.#last = undefined;
    return this;
  }

  /** Return the last N records (tail pagination). */
  last(n: number): this {
    this.#last = n;
    this.#first = undefined as unknown as number;
    return this;
  }

  /**
   * Build and return the raw params object without executing the request.
   * Useful for inspection or passing to getEvents() directly.
   */
  build(): GetEventsParams {
    const params: GetEventsParams = {};
    if (this.#contractId !== undefined) params.contractId = this.#contractId;
    if (this.#eventType !== undefined) params.eventType = this.#eventType;
    if (this.#startLedger !== undefined) params.startLedger = this.#startLedger;
    if (this.#endLedger !== undefined) params.endLedger = this.#endLedger;
    if (this.#after !== undefined) params.after = this.#after;
    if (this.#before !== undefined) params.before = this.#before;
    if (this.#last !== undefined) {
      params.last = this.#last;
    } else {
      params.first = this.#first;
    }
    return params;
  }

  /** Execute the query and return the paginated response. */
  execute(): Promise<GetEventsResponse> {
    return this.#client.getEvents(this.build());
  }

  /**
   * Execute the query with Zod payload validation (SC-1419).
   * Validates each event's payload against the provided schema when given.
   */
  async query<T = unknown>(
    params: GetEventsParams,
    schema?: ZodType<T>
  ): Promise<ContractEvent<T>[]> {
    const response = await this.#client.getEvents(params);
    if (!schema) return response.items as ContractEvent<T>[];
    return response.items.map((event) => ({
      ...event,
      value: schema.parse(event.value),
    })) as ContractEvent<T>[];
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ContractQueryBuilder
// ─────────────────────────────────────────────────────────────────────────────

export class ContractQueryBuilder {
  readonly #client: SoroScanClient;
  #type?: string;
  #creator?: string;
  #search?: string;
  #verified?: boolean;
  #after?: string;
  #before?: string;
  #first: number = 50;

  constructor(client: SoroScanClient) {
    this.#client = client;
  }

  /** Filter by contract type (e.g. "token", "dex"). */
  filterByType(type: string): this {
    this.#type = type;
    return this;
  }

  /** Filter by creator address. */
  filterByCreator(creator: string): this {
    this.#creator = creator;
    return this;
  }

  /** Show only verified contracts. */
  filterByVerified(verified: boolean = true): this {
    this.#verified = verified;
    return this;
  }

  /** Search by label or contract ID (partial match). */
  search(query: string): this {
    this.#search = query;
    return this;
  }

  /** Set cursor for forward pagination. */
  after(cursor: string): this {
    this.#after = cursor;
    this.#before = undefined;
    return this;
  }

  /** Set cursor for backward pagination. */
  before(cursor: string): this {
    this.#before = cursor;
    this.#after = undefined;
    return this;
  }

  /**
   * Set page size (number of results to return).
   *
   * @param limit - max records to return (default 50)
   */
  paginate(limit: number = 50): this {
    this.#first = limit;
    return this;
  }

  /** Alias for paginate(). */
  first(n: number): this {
    this.#first = n;
    return this;
  }

  /**
   * Build and return the raw params object without executing the request.
   */
  build(): GetContractsParams {
    const params: GetContractsParams = {};
    if (this.#type !== undefined) params.type = this.#type as GetContractsParams["type"];
    if (this.#creator !== undefined) params.creator = this.#creator;
    if (this.#search !== undefined) params.search = this.#search;
    if (this.#verified !== undefined) params.verified = this.#verified;
    if (this.#after !== undefined) params.after = this.#after;
    if (this.#before !== undefined) params.before = this.#before;
    params.first = this.#first;
    return params;
  }

  /** Execute the query and return the paginated response. */
  execute(): Promise<GetContractsResponse> {
    return this.#client.getContracts(this.build());
  }
}
