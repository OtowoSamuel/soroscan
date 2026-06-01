import React from "react"
import { render, screen, fireEvent, within } from "@testing-library/react"
import {
  WebhookFilterExpressionBuilder,
  emptyExpression,
  serializeExpression,
  type FilterExpression,
} from "@/components/ui/WebhookFilterExpressionBuilder"

const mockOnChange = jest.fn()
const mockOnApply = jest.fn()

beforeEach(() => {
  mockOnChange.mockClear()
  mockOnApply.mockClear()
})

function renderBuilder(props: Partial<React.ComponentProps<typeof WebhookFilterExpressionBuilder>> = {}) {
  return render(
    <WebhookFilterExpressionBuilder
      onChange={mockOnChange}
      onApply={mockOnApply}
      {...props}
    />
  )
}

// ── Unit: serializer ─────────────────────────────────────────────────────────

describe("serializeExpression", () => {
  it("serializes a simple eq condition", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "SWAP_COMPLETE" },
        ],
      },
    }
    expect(serializeExpression(expr)).toBe('event_type = "SWAP_COMPLETE"')
  })

  it("serializes AND group with two conditions", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "SWAP_COMPLETE" },
          { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "1000" },
        ],
      },
    }
    const result = serializeExpression(expr)
    expect(result).toContain("AND")
    expect(result).toContain("event_type")
    expect(result).toContain("amount")
  })

  it("serializes OR group", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "OR",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "SWAP_COMPLETE" },
          { id: "c2", kind: "condition", field: "event_type", operator: "eq", value: "LIQUIDITY_ADD" },
        ],
      },
    }
    expect(serializeExpression(expr)).toContain("OR")
  })

  it("serializes exists operator without value", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "contract_id", operator: "exists", value: "" },
        ],
      },
    }
    expect(serializeExpression(expr)).toBe("EXISTS(contract_id)")
  })

  it("serializes IN operator with csv values", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "in", value: "SWAP_COMPLETE, LIQUIDITY_ADD" },
        ],
      },
    }
    const result = serializeExpression(expr)
    expect(result).toContain("IN")
    expect(result).toContain("SWAP_COMPLETE")
    expect(result).toContain("LIQUIDITY_ADD")
  })

  it("wraps nested group in parentheses", () => {
    const expr: FilterExpression = {
      root: {
        id: "g1",
        kind: "group",
        logic: "AND",
        children: [
          { id: "c1", kind: "condition", field: "event_type", operator: "eq", value: "SWAP_COMPLETE" },
          {
            id: "g2",
            kind: "group",
            logic: "OR",
            children: [
              { id: "c2", kind: "condition", field: "amount", operator: "gt", value: "1000" },
              { id: "c3", kind: "condition", field: "amount", operator: "lt", value: "50" },
            ],
          },
        ],
      },
    }
    const result = serializeExpression(expr)
    expect(result).toContain("(")
    expect(result).toContain("AND")
    expect(result).toContain("OR")
  })

  it("returns (empty) for empty root group", () => {
    const expr: FilterExpression = {
      root: { id: "g1", kind: "group", logic: "AND", children: [] },
    }
    expect(serializeExpression(expr)).toBe("(empty)")
  })
})

// ── Unit: emptyExpression ─────────────────────────────────────────────────────

describe("emptyExpression", () => {
  it("creates a group with one default condition", () => {
    const expr = emptyExpression()
    expect(expr.root.kind).toBe("group")
    expect(expr.root.children).toHaveLength(1)
    expect(expr.root.children[0].kind).toBe("condition")
  })

  it("defaults to AND logic", () => {
    expect(emptyExpression().root.logic).toBe("AND")
  })
})

// ── Component tests ───────────────────────────────────────────────────────────

describe("WebhookFilterExpressionBuilder component", () => {
  it("renders accessible group and at least one condition row", () => {
    renderBuilder()
    expect(screen.getByRole("group", { name: /webhook filter expression builder/i })).toBeInTheDocument()
    expect(screen.getAllByTestId("webhook-filter-condition")).toHaveLength(1)
  })

  it("renders root group with [ROOT] label", () => {
    renderBuilder()
    expect(screen.getByTestId("webhook-filter-root-group")).toBeInTheDocument()
    expect(screen.getByText("[ROOT]")).toBeInTheDocument()
  })

  it("renders AND and OR logic toggle buttons", () => {
    renderBuilder()
    expect(screen.getByTestId("logic-and-btn")).toBeInTheDocument()
    expect(screen.getByTestId("logic-or-btn")).toBeInTheDocument()
  })

  it("AND is pressed by default", () => {
    renderBuilder()
    expect(screen.getByTestId("logic-and-btn")).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByTestId("logic-or-btn")).toHaveAttribute("aria-pressed", "false")
  })

  it("switches to OR logic when OR is clicked", () => {
    renderBuilder()
    fireEvent.click(screen.getByTestId("logic-or-btn"))
    expect(screen.getByTestId("logic-or-btn")).toHaveAttribute("aria-pressed", "true")
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({
        root: expect.objectContaining({ logic: "OR" }),
      })
    )
  })

  it("adds a condition when ADD_CONDITION button is clicked", () => {
    renderBuilder()
    fireEvent.click(screen.getByTestId("add-condition-btn"))
    expect(screen.getAllByTestId("webhook-filter-condition")).toHaveLength(2)
    expect(mockOnChange).toHaveBeenCalled()
  })

  it("removes a condition when the remove button is clicked", () => {
    renderBuilder()
    // Add a second condition first
    fireEvent.click(screen.getByTestId("add-condition-btn"))
    expect(screen.getAllByTestId("webhook-filter-condition")).toHaveLength(2)
    // Remove the first
    fireEvent.click(screen.getAllByTestId("remove-condition-btn")[0])
    expect(screen.getAllByTestId("webhook-filter-condition")).toHaveLength(1)
  })

  it("adds a sub-group when GROUP button is clicked", () => {
    renderBuilder()
    fireEvent.click(screen.getByTestId("add-group-btn"))
    expect(screen.getByTestId("webhook-filter-sub-group")).toBeInTheDocument()
  })

  it("updates field select and calls onChange", () => {
    renderBuilder()
    const fieldSelect = screen.getAllByLabelText("Filter field")[0]
    fireEvent.change(fieldSelect, { target: { value: "amount" } })
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({
        root: expect.objectContaining({
          children: expect.arrayContaining([
            expect.objectContaining({ field: "amount" }),
          ]),
        }),
      })
    )
  })

  it("updates operator select and calls onChange", () => {
    renderBuilder()
    const opSelect = screen.getAllByLabelText("Filter operator")[0]
    fireEvent.change(opSelect, { target: { value: "neq" } })
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({
        root: expect.objectContaining({
          children: expect.arrayContaining([
            expect.objectContaining({ operator: "neq" }),
          ]),
        }),
      })
    )
  })

  it("updates value input and calls onChange", () => {
    renderBuilder()
    const valueInput = screen.getAllByLabelText("Filter value")[0]
    fireEvent.change(valueInput, { target: { value: "SWAP_COMPLETE" } })
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({
        root: expect.objectContaining({
          children: expect.arrayContaining([
            expect.objectContaining({ value: "SWAP_COMPLETE" }),
          ]),
        }),
      })
    )
  })

  it("renders live expression preview", () => {
    renderBuilder()
    expect(screen.getByTestId("filter-expression-preview")).toBeInTheDocument()
  })

  it("updates expression preview when value changes", () => {
    renderBuilder()
    // Switch the default enum field to a string field so we get a text input
    const fieldSelect = screen.getAllByLabelText("Filter field")[0]
    fireEvent.change(fieldSelect, { target: { value: "contract_id" } })
    const valueInput = screen.getAllByLabelText("Filter value")[0]
    fireEvent.change(valueInput, { target: { value: "myvalue" } })
    const preview = screen.getByTestId("filter-expression-preview")
    expect(preview.textContent).toContain("myvalue")
  })

  it("calls onApply with expression when APPLY_FILTER is clicked", () => {
    renderBuilder()
    fireEvent.click(screen.getByTestId("apply-expression-btn"))
    expect(mockOnApply).toHaveBeenCalledTimes(1)
    expect(mockOnApply).toHaveBeenCalledWith(
      expect.objectContaining({ root: expect.any(Object) }),
      expect.any(String)
    )
  })

  it("resets to empty expression on RESET click", () => {
    renderBuilder()
    // Add extra condition
    fireEvent.click(screen.getByTestId("add-condition-btn"))
    expect(screen.getAllByTestId("webhook-filter-condition")).toHaveLength(2)
    fireEvent.click(screen.getByTestId("reset-expression-btn"))
    expect(screen.getAllByTestId("webhook-filter-condition")).toHaveLength(1)
  })

  it("syncs external value prop when changed", () => {
    const initial = emptyExpression()
    const { rerender } = renderBuilder({ value: initial })
    const newExpr: FilterExpression = {
      root: {
        id: "g_new",
        kind: "group",
        logic: "OR",
        children: [
          { id: "c_new", kind: "condition", field: "amount", operator: "gt", value: "500" },
        ],
      },
    }
    rerender(
      <WebhookFilterExpressionBuilder
        value={newExpr}
        onChange={mockOnChange}
        onApply={mockOnApply}
      />
    )
    expect(screen.getByTestId("logic-or-btn")).toHaveAttribute("aria-pressed", "true")
  })
})
