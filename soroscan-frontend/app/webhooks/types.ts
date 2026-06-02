export type WebhookStatus = "ACTIVE" | "SUSPENDED" | "FAILED"

export type EventType =
  | "ALL"
  | "SWAP_COMPLETE"
  | "LIQUIDITY_ADD"
  | "VAULT_DEPOSIT"
  | "GOV_PROPOSAL"
  | "YIELD_CLAIMED"
  | "ORACLE_UPDATE"
  | "STAKING_LOCK"

export interface Webhook {
  id: string
  url: string
  eventTypes: EventType[]
  contractFilter?: string
  /** Serialized filter expression built by the visual filter builder */
  filterExpression?: string
  status: WebhookStatus
  isActive: boolean
  createdAt: string
  lastDelivery?: string
  lastStatusCode?: number
  successRate: number // 0–100
  timeoutSeconds: number
  secret: string
  customHeaders?: Record<string, string>
  totalDeliveries: number
  failureCount?: number
  lastDeliverySuccess?: boolean
}

export interface DeliveryLog {
  id: string
  webhookId: string
  timestamp: string
  statusCode: number
  responseTimeMs: number
  attempt: number
  errorMessage?: string
  eventType: EventType
  contractId: string
}

export type SortField = "timestamp" | "statusCode" | "responseTimeMs" | "attempt"
export type SortDir = "asc" | "desc"
export type StatusFilter = "ALL" | "2xx" | "4xx" | "5xx"
