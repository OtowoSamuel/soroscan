"use client"

import * as React from "react"
import { CheckCircle2, XCircle, AlertTriangle, Play, RotateCcw } from "lucide-react"
import type { FilterExpression, FilterNode, FilterGroup, FilterCondition, Operator } from "./WebhookFilterExpressionBuilder"
import { serializeExpression } from "./WebhookFilterExpressionBuilder"

// ── Types ──────────────────────────────────────────────────────────────────

export interface TestResult {
  passed: boolean
  conditionResults: ConditionResult[]
  error?: string
  serialized: string
}

export interface ConditionResult {
  conditionId: string
  field: string
  operator: Operator
  value: string
  actual: unknown
  passed: boolean
  reason: string
}

// ── Evaluator ──────────────────────────────────────────────────────────────

function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((cur, key) => {
    if (cur !== null && cur !== undefined && typeof cur === "object") {
      return (cur as Record<string, unknown>)[key]
    }
    return undefined
  }, obj)
}

function evaluateCondition(
  cond: FilterCondition,
  payload: Record<string, unknown>
): ConditionResult {
  const actual = getNestedValue(payload, cond.field)
  const actualStr = String(actual ?? "")
  const v = cond.value

  let passed = false
  let reason = ""

  switch (cond.operator) {
    case "eq":
      passed = actualStr === v
      reason = passed ? `${cond.field} = "${v}"` : `${cond.field} is "${actualStr}", expected "${v}"`
      break
    case "neq":
      passed = actualStr !== v
      reason = passed ? `${cond.field} ≠ "${v}"` : `${cond.field} equals "${v}" (should differ)`
      break
    case "contains":
      passed = actualStr.includes(v)
      reason = passed ? `"${actualStr}" contains "${v}"` : `"${actualStr}" does not contain "${v}"`
      break
    case "not_contains":
      passed = !actualStr.includes(v)
      reason = passed ? `"${actualStr}" does not contain "${v}"` : `"${actualStr}" contains "${v}"`
      break
    case "starts_with":
      passed = actualStr.startsWith(v)
      reason = passed ? `"${actualStr}" starts with "${v}"` : `"${actualStr}" does not start with "${v}"`
      break
    case "ends_with":
      passed = actualStr.endsWith(v)
      reason = passed ? `"${actualStr}" ends with "${v}"` : `"${actualStr}" does not end with "${v}"`
      break
    case "gt":
      passed = Number(actual) > Number(v)
      reason = passed ? `${actual} > ${v}` : `${actual} is not > ${v}`
      break
    case "gte":
      passed = Number(actual) >= Number(v)
      reason = passed ? `${actual} >= ${v}` : `${actual} is not >= ${v}`
      break
    case "lt":
      passed = Number(actual) < Number(v)
      reason = passed ? `${actual} < ${v}` : `${actual} is not < ${v}`
      break
    case "lte":
      passed = Number(actual) <= Number(v)
      reason = passed ? `${actual} <= ${v}` : `${actual} is not <= ${v}`
      break
    case "in": {
      const vals = v.split(",").map((s) => s.trim())
      passed = vals.includes(actualStr)
      reason = passed ? `"${actualStr}" is in [${vals.join(", ")}]` : `"${actualStr}" not in [${vals.join(", ")}]`
      break
    }
    case "not_in": {
      const vals = v.split(",").map((s) => s.trim())
      passed = !vals.includes(actualStr)
      reason = passed ? `"${actualStr}" not in [${vals.join(", ")}]` : `"${actualStr}" is in [${vals.join(", ")}]`
      break
    }
    case "exists":
      passed = actual !== undefined && actual !== null && actual !== ""
      reason = passed ? `${cond.field} exists` : `${cond.field} is absent or empty`
      break
    case "not_exists":
      passed = actual === undefined || actual === null || actual === ""
      reason = passed ? `${cond.field} is absent` : `${cond.field} exists with value "${actualStr}"`
      break
    default:
      passed = false
      reason = `Unknown operator "${cond.operator}"`
  }

  return { conditionId: cond.id, field: cond.field, operator: cond.operator, value: cond.value, actual, passed, reason }
}

function evaluateGroup(
  group: FilterGroup,
  payload: Record<string, unknown>,
  results: ConditionResult[]
): boolean {
  if (group.children.length === 0) return true

  const childResults: boolean[] = group.children.map((child) => evaluateNode(child, payload, results))

  if (group.logic === "AND") return childResults.every(Boolean)
  return childResults.some(Boolean)
}

function evaluateNode(
  node: FilterNode,
  payload: Record<string, unknown>,
  results: ConditionResult[]
): boolean {
  if (node.kind === "condition") {
    const r = evaluateCondition(node, payload)
    results.push(r)
    return r.passed
  }
  return evaluateGroup(node, payload, results)
}

export function evaluateExpression(expr: FilterExpression, payload: Record<string, unknown>): TestResult {
  const conditionResults: ConditionResult[] = []
  try {
    const passed = evaluateGroup(expr.root, payload, conditionResults)
    return { passed, conditionResults, serialized: serializeExpression(expr) }
  } catch (err) {
    return {
      passed: false,
      conditionResults,
      error: err instanceof Error ? err.message : String(err),
      serialized: serializeExpression(expr),
    }
  }
}

// ── Default sample payload ─────────────────────────────────────────────────

const DEFAULT_SAMPLE = JSON.stringify(
  {
    event_type: "SWAP_COMPLETE",
    contract_id: "CABC...9X4Z",
    amount: 1500,
    ledger: 52300,
    timestamp: 1716000000,
    from_address: "GDEX...A1B2",
    to_address: "GCOL...K9L0",
    asset_code: "USDC",
    topic: "soroscan/swap",
    success: true,
  },
  null,
  2
)

// ── Component ──────────────────────────────────────────────────────────────

export interface FilterExpressionTesterProps {
  expression: FilterExpression
  onClose?: () => void
}

export function FilterExpressionTester({ expression, onClose }: FilterExpressionTesterProps) {
  const [sampleJson, setSampleJson] = React.useState(DEFAULT_SAMPLE)
  const [jsonError, setJsonError] = React.useState<string | null>(null)
  const [result, setResult] = React.useState<TestResult | null>(null)
  const [running, setRunning] = React.useState(false)

  const handleRun = () => {
    setJsonError(null)
    setResult(null)

    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(sampleJson)
    } catch {
      setJsonError("Invalid JSON — fix the sample payload and try again.")
      return
    }

    setRunning(true)
    // Slight artificial delay for UX
    setTimeout(() => {
      const r = evaluateExpression(expression, payload)
      setResult(r)
      setRunning(false)
    }, 300)
  }

  const handleReset = () => {
    setSampleJson(DEFAULT_SAMPLE)
    setResult(null)
    setJsonError(null)
  }

  const passed = result?.conditionResults.filter((r) => r.passed).length ?? 0
  const failed = result?.conditionResults.filter((r) => !r.passed).length ?? 0

  return (
    <div
      className="font-terminal-mono text-[11px] space-y-4"
      data-testid="filter-expression-tester"
    >
      {/* Expression being tested */}
      <div className="border border-terminal-green/20 bg-terminal-green/3 px-3 py-2 space-y-1">
        <div className="text-[9px] text-terminal-gray tracking-widest">TESTING_EXPRESSION</div>
        <div className="text-terminal-cyan text-[10px] break-all leading-relaxed">
          {serializeExpression(expression) || "(empty)"}
        </div>
      </div>

      {/* Sample JSON editor */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label
            htmlFor="sample-payload-input"
            className="text-[9px] text-terminal-gray tracking-widest"
          >
            SAMPLE_PAYLOAD (JSON)
          </label>
          <button
            type="button"
            onClick={handleReset}
            className="text-[9px] text-terminal-gray hover:text-terminal-cyan transition-colors flex items-center gap-1"
            aria-label="Reset sample payload"
          >
            <RotateCcw size={10} /> RESET
          </button>
        </div>
        <textarea
          id="sample-payload-input"
          value={sampleJson}
          onChange={(e) => {
            setSampleJson(e.target.value)
            setJsonError(null)
            setResult(null)
          }}
          rows={10}
          spellCheck={false}
          className="w-full bg-terminal-black border border-terminal-green/30 text-terminal-green text-[10px] leading-relaxed px-3 py-2 focus:outline-none focus:border-terminal-green resize-none font-terminal-mono placeholder:text-terminal-gray/40 hover:border-terminal-green/50 transition-colors"
          aria-label="Sample JSON payload"
          aria-describedby={jsonError ? "json-error-msg" : undefined}
        />
        {jsonError && (
          <p id="json-error-msg" className="text-terminal-danger text-[10px] flex items-center gap-1">
            <AlertTriangle size={11} /> {jsonError}
          </p>
        )}
      </div>

      {/* Run button */}
      <button
        type="button"
        onClick={handleRun}
        disabled={running}
        className="w-full border border-terminal-green text-terminal-green py-2 text-[11px] tracking-widest hover:bg-terminal-green/10 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
        data-testid="run-test-btn"
      >
        {running ? (
          <>
            <span className="animate-spin inline-block w-3 h-3 border border-terminal-green border-t-transparent rounded-full" />
            EVALUATING...
          </>
        ) : (
          <>
            <Play size={12} /> RUN_TEST
          </>
        )}
      </button>

      {/* Results */}
      {result && (
        <div className="space-y-3" data-testid="test-results">
          {/* Overall verdict */}
          <div
            className={`flex items-center gap-3 px-4 py-3 border ${
              result.error
                ? "border-terminal-yellow/40 bg-terminal-yellow/5"
                : result.passed
                  ? "border-terminal-green/50 bg-terminal-green/8"
                  : "border-terminal-danger/50 bg-terminal-danger/8"
            }`}
            data-testid="test-verdict"
          >
            {result.error ? (
              <AlertTriangle size={18} className="text-terminal-yellow flex-shrink-0" />
            ) : result.passed ? (
              <CheckCircle2 size={18} className="text-terminal-green flex-shrink-0" />
            ) : (
              <XCircle size={18} className="text-terminal-danger flex-shrink-0" />
            )}
            <div>
              <div className={`text-sm font-bold tracking-wider ${result.error ? "text-terminal-yellow" : result.passed ? "text-terminal-green" : "text-terminal-danger"}`}>
                {result.error ? "EVAL_ERROR" : result.passed ? "FILTER_MATCH — event would be delivered" : "NO_MATCH — event would be dropped"}
              </div>
              {!result.error && (
                <div className="text-[9px] text-terminal-gray mt-0.5">
                  {passed} passed · {failed} failed · {result.conditionResults.length} total conditions
                </div>
              )}
              {result.error && (
                <div className="text-[9px] text-terminal-yellow/80 mt-0.5">{result.error}</div>
              )}
            </div>
          </div>

          {/* Per-condition results */}
          {result.conditionResults.length > 0 && (
            <div className="space-y-1">
              <div className="text-[9px] text-terminal-gray tracking-widest px-1">
                CONDITION_RESULTS
              </div>
              {result.conditionResults.map((cr) => (
                <div
                  key={cr.conditionId}
                  className={`flex items-start gap-2 px-3 py-2 border ${
                    cr.passed ? "border-terminal-green/20 bg-terminal-green/3" : "border-terminal-danger/20 bg-terminal-danger/3"
                  }`}
                  data-testid="condition-result-row"
                >
                  {cr.passed ? (
                    <CheckCircle2 size={12} className="text-terminal-green mt-0.5 flex-shrink-0" />
                  ) : (
                    <XCircle size={12} className="text-terminal-danger mt-0.5 flex-shrink-0" />
                  )}
                  <div className="space-y-0.5 min-w-0">
                    <div className="text-[10px] text-terminal-cyan font-bold">
                      {cr.field}
                      <span className="text-terminal-gray font-normal mx-1">{cr.operator}</span>
                      <span className="text-terminal-green">{cr.value || "(any)"}</span>
                    </div>
                    <div className="text-[9px] text-terminal-gray">
                      actual: <span className="text-terminal-cyan/80">{JSON.stringify(cr.actual)}</span>
                    </div>
                    <div className={`text-[9px] ${cr.passed ? "text-terminal-green/70" : "text-terminal-danger/70"}`}>
                      {cr.reason}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
