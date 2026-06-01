"use client"

import * as React from "react"
import { Wand2 } from "lucide-react"
import { Modal } from "@/components/terminal/Modal"
import { Input } from "@/components/terminal/Input"
import { Button } from "@/components/terminal/Button"
import { FilterBuilderModal } from "./FilterBuilderModal"
import type { Webhook, EventType, WebhookStatus } from "../types"
import type { FilterExpression } from "@/components/ui/WebhookFilterExpressionBuilder"

const ALL_EVENT_TYPES: EventType[] = [
  "ALL",
  "SWAP_COMPLETE",
  "LIQUIDITY_ADD",
  "VAULT_DEPOSIT",
  "GOV_PROPOSAL",
  "YIELD_CLAIMED",
  "ORACLE_UPDATE",
  "STAKING_LOCK",
]

interface CreateWebhookModalProps {
  isOpen: boolean
  onClose: () => void
  onCreate: (webhook: Omit<Webhook, "id" | "createdAt" | "totalDeliveries" | "secret" | "successRate">) => void
}

function isValidUrl(str: string): boolean {
  try {
    const u = new URL(str)
    return u.protocol === "http:" || u.protocol === "https:"
  } catch {
    return false
  }
}

export function CreateWebhookModal({ isOpen, onClose, onCreate }: CreateWebhookModalProps) {
  const [url, setUrl] = React.useState("")
  const [urlTouched, setUrlTouched] = React.useState(false)
  const [selectedTypes, setSelectedTypes] = React.useState<EventType[]>(["ALL"])
  const [contractFilter, setContractFilter] = React.useState("")
  const [status, setStatus] = React.useState<WebhookStatus>("ACTIVE")
  const [timeoutInput, setTimeoutInput] = React.useState("30")
  const [timeoutTouched, setTimeoutTouched] = React.useState(false)
  const [submitting, setSubmitting] = React.useState(false)

  // Filter expression state
  const [filterExpression, setFilterExpression] = React.useState<FilterExpression | undefined>(undefined)
  const [filterExpressionStr, setFilterExpressionStr] = React.useState<string>("")
  const [filterBuilderOpen, setFilterBuilderOpen] = React.useState(false)

  const urlValid = isValidUrl(url)
  const timeoutValue = Number(timeoutInput)
  const timeoutValid = Number.isInteger(timeoutValue) && timeoutValue >= 5 && timeoutValue <= 60
  const urlError = urlTouched && !urlValid ? "Must be a valid https:// URL" : null
  const timeoutError = timeoutTouched && !timeoutValid ? "Timeout must be a whole number between 5 and 60 seconds." : null

  const toggleType = (t: EventType) => {
    if (t === "ALL") {
      setSelectedTypes(["ALL"])
      return
    }
    setSelectedTypes((prev) => {
      const without = prev.filter((x) => x !== "ALL")
      return without.includes(t) ? without.filter((x) => x !== t) : [...without, t]
    })
  }

  const handleSaveFilter = (exprStr: string, expr: FilterExpression) => {
    setFilterExpressionStr(exprStr)
    setFilterExpression(expr)
  }

  const handleClearFilter = () => {
    setFilterExpression(undefined)
    setFilterExpressionStr("")
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!urlValid) { setUrlTouched(true); return }
    if (!urlValid || !timeoutValid) {
      setUrlTouched(true)
      setTimeoutTouched(true)
      return
    }

    setSubmitting(true)
    setTimeout(() => {
      onCreate({
        url,
        eventTypes: selectedTypes.length === 0 ? ["ALL"] : selectedTypes,
        contractFilter: contractFilter.trim() || undefined,
        status,
        timeoutSeconds: timeoutValue,
        filterExpression: filterExpressionStr || undefined,
      })
      // reset
      setUrl(""); setUrlTouched(false); setSelectedTypes(["ALL"])
      setContractFilter(""); setStatus("ACTIVE"); setTimeoutInput("30"); setTimeoutTouched(false)
      setFilterExpression(undefined); setFilterExpressionStr("")
      setSubmitting(false)
      onClose()
    }, 600)
  }

  const handleClose = () => {
    setUrl(""); setUrlTouched(false); setSelectedTypes(["ALL"])
    setContractFilter(""); setStatus("ACTIVE"); setTimeoutInput("30"); setTimeoutTouched(false)
    setFilterExpression(undefined); setFilterExpressionStr("")
    onClose()
  }

  return (
    <>
      <Modal isOpen={isOpen} onClose={handleClose} title="NEW_WEBHOOK_SUBSCRIPTION">
        <form onSubmit={handleSubmit} className="space-y-5 text-sm">
          {/* URL */}
          <div>
            <Input
              id="webhook-url-input"
              label="ENDPOINT_URL *"
              type="url"
              placeholder="https://yourapp.io/webhook"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={() => setUrlTouched(true)}
              aria-invalid={!!urlError}
            />
            {urlError && (
              <p className="text-terminal-danger text-[10px] mt-1 ml-1">{urlError}</p>
            )}
          </div>

          {/* Event timeout */}
          <div>
            <Input
              id="timeout-input"
              label="REQUEST_TIMEOUT (seconds)"
              type="number"
              min={5}
              max={60}
              step={1}
              value={timeoutInput}
              onChange={(e) => setTimeoutInput(e.target.value)}
              onBlur={() => setTimeoutTouched(true)}
              aria-invalid={!!timeoutError}
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {[10, 20, 30, 45, 60].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setTimeoutInput(String(value))
                    setTimeoutTouched(true)
                  }}
                  className="rounded border border-terminal-green/20 px-3 py-1.5 text-[11px] text-terminal-gray transition hover:border-terminal-green hover:text-terminal-green"
                >
                  {value}s
                </button>
              ))}
            </div>
            {timeoutError && (
              <p className="text-terminal-danger text-[10px] mt-1 ml-1">{timeoutError}</p>
            )}
          </div>

          {/* Event types */}
          <div className="space-y-2">
            <div className="text-xs text-terminal-cyan uppercase tracking-wider ml-1">EVENT_TYPES *</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {ALL_EVENT_TYPES.map((t) => {
                const checked = selectedTypes.includes(t)
                return (
                  <label
                    key={t}
                    className={`flex items-center gap-2 cursor-pointer border px-2 py-1.5 text-[10px] transition-colors select-none ${
                      checked
                        ? "border-terminal-green text-terminal-green bg-terminal-green/5"
                        : "border-terminal-gray/30 text-terminal-gray hover:border-terminal-green/50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleType(t)}
                      className="sr-only"
                    />
                    <span className={`w-2 h-2 border ${checked ? "bg-terminal-green border-terminal-green" : "border-terminal-gray/40"}`} />
                    {t}
                  </label>
                )
              })}
            </div>
          </div>

          {/* Contract filter */}
          <Input
            id="contract-filter-input"
            label="CONTRACT_FILTER (optional)"
            type="text"
            placeholder="CABC...9X4Z — leave blank for all contracts"
            value={contractFilter}
            onChange={(e) => setContractFilter(e.target.value)}
          />

          {/* Filter expression builder */}
          <div className="space-y-2">
            <div className="text-xs text-terminal-cyan uppercase tracking-wider ml-1">
              FILTER_EXPRESSION (optional)
            </div>
            {filterExpressionStr ? (
              <div className="border border-terminal-green/30 bg-terminal-green/3 p-3 space-y-2">
                <div className="text-[9px] text-terminal-gray tracking-widest">ACTIVE_FILTER</div>
                <div
                  className="text-[10px] text-terminal-cyan break-all leading-relaxed"
                  data-testid="active-filter-expression"
                >
                  {filterExpressionStr}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setFilterBuilderOpen(true)}
                    className="text-[9px] px-3 py-1 border border-terminal-green/30 text-terminal-green hover:border-terminal-green hover:bg-terminal-green/5 transition-colors flex items-center gap-1"
                    data-testid="edit-filter-btn"
                  >
                    <Wand2 size={10} /> EDIT_FILTER
                  </button>
                  <button
                    type="button"
                    onClick={handleClearFilter}
                    className="text-[9px] px-3 py-1 border border-terminal-danger/30 text-terminal-danger hover:border-terminal-danger hover:bg-terminal-danger/5 transition-colors"
                    data-testid="clear-filter-btn"
                  >
                    CLEAR
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setFilterBuilderOpen(true)}
                className="w-full border border-dashed border-terminal-green/30 text-terminal-gray hover:border-terminal-green hover:text-terminal-green transition-colors py-3 text-[11px] tracking-widest flex items-center justify-center gap-2"
                data-testid="open-filter-builder-btn"
              >
                <Wand2 size={13} />
                BUILD_FILTER_EXPRESSION
              </button>
            )}
            <p className="text-[9px] text-terminal-gray/60 ml-1">
              Define custom field conditions to filter which events trigger this webhook.
            </p>
          </div>

          {/* Status */}
          <div className="space-y-2">
            <div className="text-xs text-terminal-cyan uppercase tracking-wider ml-1">INITIAL_STATUS</div>
            <div className="flex gap-4">
              {(["ACTIVE", "SUSPENDED"] as const).map((s) => (
                <label key={s} className="flex items-center gap-2 cursor-pointer text-[11px] select-none">
                  <input
                    type="radio"
                    name="status"
                    value={s}
                    checked={status === s}
                    onChange={() => setStatus(s)}
                    className="sr-only"
                  />
                  <span className={`w-3 h-3 border-2 rounded-full ${status === s ? "border-terminal-green bg-terminal-green" : "border-terminal-gray/40"}`} />
                  <span className={status === s ? "text-terminal-green" : "text-terminal-gray"}>{s}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Submit */}
          <div className="flex gap-3 pt-2">
            <Button
              type="submit"
              variant="primary"
              disabled={submitting || (urlTouched && !urlValid)}
              className="flex-1"
            >
              {submitting ? "CREATING..." : "CREATE_WEBHOOK"}
            </Button>
            <Button type="button" variant="danger" onClick={handleClose}>
              CANCEL
            </Button>
          </div>
        </form>
      </Modal>

      {/* Filter expression builder modal */}
      <FilterBuilderModal
        isOpen={filterBuilderOpen}
        onClose={() => setFilterBuilderOpen(false)}
        onSave={handleSaveFilter}
        initialExpression={filterExpression}
      />
    </>
  )
}
