import React from "react"
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react"
import { FilterExpressionTester, evaluateExpression } from "@/components/ui/FilterExpressionTester"
import { emptyExpression, type FilterExpression } from "@/components/ui/WebhookFilterExpressionBuilder"

// ── Unit: evaluateExpression ──────────────────────────────────────────────────

describe("evaluateExpression", () => {
  const payload = {
    event_type: "SWAP_COMPLETE",
    contract_id: "CABC...9X4Z",
    amount: 1500,
    ledger: 52300,
    success: true,
    from_address: "GDEX...A1B2",
    topic: "soroscan/swap",
  }

  function makeExpr(field: string, operator: string, value: string): FilterExpression {
    return {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field, operator: operator as never, value },
        ],
      },
    }
  }

  it("passes eq condition when values match", () => {
    const result = evaluateExpression(makeExpr("event_type", "eq", "SWAP_COMPLETE"), payload)
    expect(result.passed).toBe(true)
    expect(result.conditionResults[0].passed).toBe(true)
  })

  it("fails eq condition when values differ", () => {
    const result = evaluateExpression(makeExpr("event_type", "eq", "LIQUIDITY_ADD"), payload)
    expect(result.passed).toBe(false)
  })

  it("passes neq condition when values differ", () => {
    const result = evaluateExpression(makeExpr("event_type", "neq", "LIQUIDITY_ADD"), payload)
    expect(result.passed).toBe(true)
  })

  it("passes contains condition", () => {
    const result = evaluateExpression(makeExpr("topic", "contains", "swap"), payload)
    expect(result.passed).toBe(true)
  })

  it("fails not_contains when value is present", () => {
    const result = evaluateExpression(makeExpr("topic", "not_contains", "swap"), payload)
    expect(result.passed).toBe(false)
  })

  it("passes starts_with", () => {
    const result = evaluateExpression(makeExpr("topic", "starts_with", "soroscan"), payload)
    expect(result.passed).toBe(true)
  })

  it("passes ends_with", () => {
    const result = evaluateExpression(makeExpr("topic", "ends_with", "swap"), payload)
    expect(result.passed).toBe(true)
  })

  it("passes gt condition for numeric field", () => {
    const result = evaluateExpression(makeExpr("amount", "gt", "1000"), payload)
    expect(result.passed).toBe(true)
  })

  it("fails gt condition when value is not greater", () => {
    const result = evaluateExpression(makeExpr("amount", "gt", "2000"), payload)
    expect(result.passed).toBe(false)
  })

  it("passes gte condition at boundary", () => {
    const result = evaluateExpression(makeExpr("amount", "gte", "1500"), payload)
    expect(result.passed).toBe(true)
  })

  it("passes lt condition", () => {
    const result = evaluateExpression(makeExpr("ledger", "lt", "60000"), payload)
    expect(result.passed).toBe(true)
  })

  it("passes lte condition at boundary", () => {
    const result = evaluateExpression(makeExpr("ledger", "lte", "52300"), payload)
    expect(result.passed).toBe(true)
  })

  it("passes in condition when value is in list", () => {
    const result = evaluateExpression(
      makeExpr("event_type", "in", "SWAP_COMPLETE, LIQUIDITY_ADD"),
      payload
    )
    expect(result.passed).toBe(true)
  })

  it("fails in condition when value is not in list", () => {
    const result = evaluateExpression(
      makeExpr("event_type", "in", "GOV_PROPOSAL, ORACLE_UPDATE"),
      payload
    )
    expect(result.passed).toBe(false)
  })

  it("passes not_in when value is absent", () => {
    const result = evaluateExpression(
      makeExpr("event_type", "not_in", "GOV_PROPOSAL, ORACLE_UPDATE"),
      payload
    )
    expect(result.passed).toBe(true)
  })

  it("passes exists when field is present", () => {
    const result = evaluateExpression(makeExpr("contract_id", "exists", ""), payload)
    expect(result.passed).toBe(true)
  })

  it("fails exists when field is absent", () => {
    const result = evaluateExpression(makeExpr("nonexistent_field", "exists", ""), payload)
    expect(result.passed).toBe(false)
  })

  it("passes not_exists when field is absent", () => {
    const result = evaluateExpression(makeExpr("nonexistent_field", "not_exists", ""), payload)
    expect(result.passed).toBe(true)
  })

  it("evaluates AND group: all must pass", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "SWAP_COMPLETE" },
          { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "999" },
        ],
      },
    }
    const result = evaluateExpression(expr, payload)
    expect(result.passed).toBe(true)
    expect(result.conditionResults).toHaveLength(2)
    expect(result.conditionResults.every((r) => r.passed)).toBe(true)
  })

  it("fails AND group when one condition fails", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "SWAP_COMPLETE" },
          { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "99999" },
        ],
      },
    }
    const result = evaluateExpression(expr, payload)
    expect(result.passed).toBe(false)
    expect(result.conditionResults.some((r) => r.passed)).toBe(true)
    expect(result.conditionResults.some((r) => !r.passed)).toBe(true)
  })

  it("passes OR group when only one condition passes", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "OR",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "LIQUIDITY_ADD" },
          { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "999" },
        ],
      },
    }
    const result = evaluateExpression(expr, payload)
    expect(result.passed).toBe(true)
  })

  it("fails OR group when all conditions fail", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "OR",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "LIQUIDITY_ADD" },
          { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "99999" },
        ],
      },
    }
    const result = evaluateExpression(expr, payload)
    expect(result.passed).toBe(false)
  })

  it("evaluates nested groups: (A AND B) OR C", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "OR",
        children: [
          {
            id: "g2",
            kind: "group",
            logic: "AND",
            children: [
              // Both fail
              { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "LIQUIDITY_ADD" },
              { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "99999" },
            ],
          },
          // This passes
          { id: "c3", kind: "condition", field: "success", operator: "eq", value: "true" },
        ],
      },
    }
    const result = evaluateExpression(expr, payload)
    expect(result.passed).toBe(true)
  })

  it("returns conditionResults with field/operator/value/actual", () => {
    const result = evaluateExpression(makeExpr("amount", "gt", "1000"), payload)
    expect(result.conditionResults[0]).toMatchObject({
      field: "amount",
      operator: "gt",
      value: "1000",
      actual: 1500,
    })
  })

  it("includes reason string in each result", () => {
    const result = evaluateExpression(makeExpr("event_type", "eq", "SWAP_COMPLETE"), payload)
    expect(typeof result.conditionResults[0].reason).toBe("string")
    expect(result.conditionResults[0].reason.length).toBeGreaterThan(0)
  })

  it("returns serialized expression string", () => {
    const result = evaluateExpression(makeExpr("amount", "gt", "1000"), payload)
    expect(typeof result.serialized).toBe("string")
    expect(result.serialized).toContain("amount")
  })

  it("handles empty group (passes trivially)", () => {
    const emptyExpr = { root: { id: "g1", kind: "group" as const, logic: "AND" as const, children: [] } }
    const result = evaluateExpression(emptyExpr, payload)
    expect(result.passed).toBe(true)
    expect(result.conditionResults).toHaveLength(0)
  })
})

// ── Component: FilterExpressionTester ────────────────────────────────────────

describe("FilterExpressionTester component", () => {
  function makeSimpleExpr(eventType: string): FilterExpression {
    return {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: eventType },
        ],
      },
    }
  }

  it("renders the tester container", () => {
    render(<FilterExpressionTester expression={emptyExpression()} />)
    expect(screen.getByTestId("filter-expression-tester")).toBeInTheDocument()
  })

  it("renders the RUN_TEST button", () => {
    render(<FilterExpressionTester expression={emptyExpression()} />)
    expect(screen.getByTestId("run-test-btn")).toBeInTheDocument()
  })

  it("renders the sample payload textarea pre-filled with JSON", () => {
    render(<FilterExpressionTester expression={emptyExpression()} />)
    const textarea = screen.getByLabelText("Sample JSON payload")
    expect(textarea).toBeInTheDocument()
    // Should contain the default sample
    expect((textarea as HTMLTextAreaElement).value).toContain("event_type")
  })

  it("shows a passing verdict when expression matches payload", async () => {
    const expr = makeSimpleExpr("SWAP_COMPLETE") // default sample has this
    render(<FilterExpressionTester expression={expr} />)
    fireEvent.click(screen.getByTestId("run-test-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("test-verdict")).toBeInTheDocument()
    }, { timeout: 1000 })
    expect(screen.getByTestId("test-verdict").textContent).toContain("FILTER_MATCH")
  })

  it("shows a failing verdict when expression does not match payload", async () => {
    const expr = makeSimpleExpr("LIQUIDITY_ADD") // default sample has SWAP_COMPLETE
    render(<FilterExpressionTester expression={expr} />)
    fireEvent.click(screen.getByTestId("run-test-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("test-verdict")).toBeInTheDocument()
    }, { timeout: 1000 })
    expect(screen.getByTestId("test-verdict").textContent).toContain("NO_MATCH")
  })

  it("shows per-condition result rows after running", async () => {
    const expr = makeSimpleExpr("SWAP_COMPLETE")
    render(<FilterExpressionTester expression={expr} />)
    fireEvent.click(screen.getByTestId("run-test-btn"))
    await waitFor(() => {
      expect(screen.getAllByTestId("condition-result-row")).toHaveLength(1)
    }, { timeout: 1000 })
  })

  it("shows a JSON parse error when payload is invalid JSON", () => {
    render(<FilterExpressionTester expression={emptyExpression()} />)
    const textarea = screen.getByLabelText("Sample JSON payload")
    fireEvent.change(textarea, { target: { value: "not valid json {{" } })
    fireEvent.click(screen.getByTestId("run-test-btn"))
    expect(screen.getByText(/invalid json/i)).toBeInTheDocument()
    expect(screen.queryByTestId("test-results")).not.toBeInTheDocument()
  })

  it("resets payload to default when RESET is clicked", () => {
    render(<FilterExpressionTester expression={emptyExpression()} />)
    const textarea = screen.getByLabelText("Sample JSON payload")
    fireEvent.change(textarea, { target: { value: '{"foo":"bar"}' } })
    expect((textarea as HTMLTextAreaElement).value).toBe('{"foo":"bar"}')
    fireEvent.click(screen.getByLabelText("Reset sample payload"))
    expect((textarea as HTMLTextAreaElement).value).toContain("event_type")
  })

  it("clears results when payload is edited after running", async () => {
    const expr = makeSimpleExpr("SWAP_COMPLETE")
    render(<FilterExpressionTester expression={expr} />)
    fireEvent.click(screen.getByTestId("run-test-btn"))
    await waitFor(() => expect(screen.getByTestId("test-verdict")).toBeInTheDocument(), { timeout: 1000 })
    // Edit the textarea — results should clear
    const textarea = screen.getByLabelText("Sample JSON payload")
    fireEvent.change(textarea, { target: { value: '{"event_type":"LIQUIDITY_ADD"}' } })
    expect(screen.queryByTestId("test-results")).not.toBeInTheDocument()
  })
})
