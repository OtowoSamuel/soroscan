"use client"

import * as React from "react"
import { Plus, Trash2, ChevronDown, ChevronRight, Layers } from "lucide-react"

// ── Types ──────────────────────────────────────────────────────────────────

export type LogicOp = "AND" | "OR"
export type Operator =
  | "eq"
  | "neq"
  | "contains"
  | "not_contains"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "lt"
  | "gte"
  | "lte"
  | "in"
  | "not_in"
  | "exists"
  | "not_exists"

export type FieldType = "string" | "number" | "enum" | "boolean"

export interface FieldDef {
  key: string
  label: string
  type: FieldType
  /** Only for enum fields */
  enumValues?: string[]
}

export interface FilterCondition {
  id: string
  kind: "condition"
  field: string
  operator: Operator
  value: string
}

export interface FilterGroup {
  id: string
  kind: "group"
  logic: LogicOp
  children: FilterNode[]
}

export type FilterNode = FilterCondition | FilterGroup

export interface FilterExpression {
  root: FilterGroup
}

// ── Constants ──────────────────────────────────────────────────────────────

export const WEBHOOK_FIELDS: FieldDef[] = [
  { key: "event_type",    label: "event_type",    type: "enum", enumValues: ["SWAP_COMPLETE", "LIQUIDITY_ADD", "VAULT_DEPOSIT", "GOV_PROPOSAL", "YIELD_CLAIMED", "ORACLE_UPDATE", "STAKING_LOCK"] },
  { key: "contract_id",  label: "contract_id",   type: "string" },
  { key: "amount",       label: "amount",         type: "number" },
  { key: "ledger",       label: "ledger",         type: "number" },
  { key: "timestamp",    label: "timestamp",      type: "number" },
  { key: "from_address", label: "from_address",   type: "string" },
  { key: "to_address",   label: "to_address",     type: "string" },
  { key: "asset_code",   label: "asset_code",     type: "string" },
  { key: "topic",        label: "topic",          type: "string" },
  { key: "success",      label: "success",        type: "boolean" },
]

const STRING_OPERATORS: { value: Operator; label: string }[] = [
  { value: "eq",           label: "=" },
  { value: "neq",          label: "≠" },
  { value: "contains",     label: "contains" },
  { value: "not_contains", label: "not contains" },
  { value: "starts_with",  label: "starts with" },
  { value: "ends_with",    label: "ends with" },
  { value: "in",           label: "in (csv)" },
  { value: "not_in",       label: "not in (csv)" },
  { value: "exists",       label: "exists" },
  { value: "not_exists",   label: "not exists" },
]

const NUMBER_OPERATORS: { value: Operator; label: string }[] = [
  { value: "eq",         label: "=" },
  { value: "neq",        label: "≠" },
  { value: "gt",         label: ">" },
  { value: "gte",        label: ">=" },
  { value: "lt",         label: "<" },
  { value: "lte",        label: "<=" },
  { value: "exists",     label: "exists" },
  { value: "not_exists", label: "not exists" },
]

const ENUM_OPERATORS: { value: Operator; label: string }[] = [
  { value: "eq",     label: "=" },
  { value: "neq",    label: "≠" },
  { value: "in",     label: "in" },
  { value: "not_in", label: "not in" },
]

const BOOLEAN_OPERATORS: { value: Operator; label: string }[] = [
  { value: "eq", label: "=" },
]

function getOperatorsForField(field: FieldDef): { value: Operator; label: string }[] {
  switch (field.type) {
    case "number":  return NUMBER_OPERATORS
    case "enum":    return ENUM_OPERATORS
    case "boolean": return BOOLEAN_OPERATORS
    default:        return STRING_OPERATORS
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function uid(): string {
  return Math.random().toString(36).slice(2, 9)
}

function defaultCondition(): FilterCondition {
  return {
    id: uid(),
    kind: "condition",
    field: WEBHOOK_FIELDS[0].key,
    operator: "eq",
    value: "",
  }
}

function defaultGroup(): FilterGroup {
  return {
    id: uid(),
    kind: "group",
    logic: "AND",
    children: [defaultCondition()],
  }
}

export function emptyExpression(): FilterExpression {
  return { root: defaultGroup() }
}

// ── Expression → String serializer ────────────────────────────────────────

const OP_SYMBOLS: Record<Operator, string> = {
  eq:           "=",
  neq:          "!=",
  contains:     "~=",
  not_contains: "!~=",
  starts_with:  "^=",
  ends_with:    "$=",
  gt:           ">",
  lt:           "<",
  gte:          ">=",
  lte:          "<=",
  in:           "IN",
  not_in:       "NOT IN",
  exists:       "EXISTS",
  not_exists:   "NOT EXISTS",
}

function serializeNode(node: FilterNode): string {
  if (node.kind === "condition") {
    const op = OP_SYMBOLS[node.operator]
    if (node.operator === "exists" || node.operator === "not_exists") {
      return `${op}(${node.field})`
    }
    if (node.operator === "in" || node.operator === "not_in") {
      const vals = node.value.split(",").map((v) => `"${v.trim()}"`).join(", ")
      return `${node.field} ${op} [${vals}]`
    }
    const numFields = WEBHOOK_FIELDS.find((f) => f.key === node.field)
    const isNum = numFields?.type === "number" || numFields?.type === "boolean"
    const valStr = isNum ? node.value : `"${node.value}"`
    return `${node.field} ${op} ${valStr}`
  }
  // group
  if (node.children.length === 0) return "(empty)"
  const parts = node.children.map(serializeNode)
  const joined = parts.join(` ${node.logic} `)
  return node.children.length > 1 ? `(${joined})` : joined
}

export function serializeExpression(expr: FilterExpression): string {
  return serializeNode(expr.root)
}

// ── Immutable tree update helpers ──────────────────────────────────────────

function updateNodeInGroup(group: FilterGroup, targetId: string, updater: (node: FilterNode) => FilterNode): FilterGroup {
  return {
    ...group,
    children: group.children.map((child) => {
      if (child.id === targetId) return updater(child)
      if (child.kind === "group") return updateNodeInGroup(child, targetId, updater)
      return child
    }),
  }
}

function removeNodeFromGroup(group: FilterGroup, targetId: string): FilterGroup {
  return {
    ...group,
    children: group.children
      .filter((child) => child.id !== targetId)
      .map((child) => (child.kind === "group" ? removeNodeFromGroup(child, targetId) : child)),
  }
}

function addNodeToGroup(group: FilterGroup, targetGroupId: string, node: FilterNode): FilterGroup {
  if (group.id === targetGroupId) {
    return { ...group, children: [...group.children, node] }
  }
  return {
    ...group,
    children: group.children.map((child) =>
      child.kind === "group" ? addNodeToGroup(child, targetGroupId, node) : child
    ),
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────

interface ConditionRowProps {
  condition: FilterCondition
  depth: number
  isOnly: boolean
  onUpdate: (id: string, patch: Partial<FilterCondition>) => void
  onRemove: (id: string) => void
}

function ConditionRow({ condition, depth, isOnly, onUpdate, onRemove }: ConditionRowProps) {
  const fieldDef = WEBHOOK_FIELDS.find((f) => f.key === condition.field) ?? WEBHOOK_FIELDS[0]
  const operators = getOperatorsForField(fieldDef)
  const noValue = condition.operator === "exists" || condition.operator === "not_exists"
  const isEnum = fieldDef.type === "enum" && (condition.operator === "eq" || condition.operator === "neq")
  const isBool = fieldDef.type === "boolean"
  const isInOp = condition.operator === "in" || condition.operator === "not_in"

  const handleFieldChange = (newField: string) => {
    const newDef = WEBHOOK_FIELDS.find((f) => f.key === newField) ?? WEBHOOK_FIELDS[0]
    const newOps = getOperatorsForField(newDef)
    const validOp = newOps.find((o) => o.value === condition.operator) ? condition.operator : newOps[0].value
    onUpdate(condition.id, { field: newField, operator: validOp as Operator, value: "" })
  }

  return (
    <div
      className="flex flex-wrap items-center gap-2 py-1.5 px-2 border border-terminal-green/10 hover:border-terminal-green/30 transition-colors group/row"
      data-testid="webhook-filter-condition"
      style={{ marginLeft: `${depth * 8}px` }}
    >
      {/* Field select */}
      <select
        value={condition.field}
        onChange={(e) => handleFieldChange(e.target.value)}
        aria-label="Filter field"
        className="bg-terminal-black border border-terminal-green/40 text-terminal-green text-[11px] px-2 py-1 focus:outline-none focus:border-terminal-green cursor-pointer hover:border-terminal-green/70 transition-colors"
      >
        {WEBHOOK_FIELDS.map((f) => (
          <option key={f.key} value={f.key} className="bg-[#0a0e27]">
            {f.label}
          </option>
        ))}
      </select>

      {/* Operator select */}
      <select
        value={condition.operator}
        onChange={(e) => onUpdate(condition.id, { operator: e.target.value as Operator, value: "" })}
        aria-label="Filter operator"
        className="bg-terminal-black border border-terminal-cyan/40 text-terminal-cyan text-[11px] px-2 py-1 focus:outline-none focus:border-terminal-cyan cursor-pointer hover:border-terminal-cyan/70 transition-colors"
      >
        {operators.map((op) => (
          <option key={op.value} value={op.value} className="bg-[#0a0e27]">
            {op.label}
          </option>
        ))}
      </select>

      {/* Value input */}
      {!noValue && (
        <>
          {isEnum ? (
            <select
              value={condition.value}
              onChange={(e) => onUpdate(condition.id, { value: e.target.value })}
              aria-label="Filter value"
              className="bg-terminal-black border border-terminal-green/40 text-terminal-green text-[11px] px-2 py-1 focus:outline-none focus:border-terminal-green cursor-pointer hover:border-terminal-green/70 transition-colors"
            >
              <option value="" className="bg-[#0a0e27] text-terminal-gray">
                select...
              </option>
              {fieldDef.enumValues?.map((v) => (
                <option key={v} value={v} className="bg-[#0a0e27]">
                  {v}
                </option>
              ))}
            </select>
          ) : isBool ? (
            <select
              value={condition.value}
              onChange={(e) => onUpdate(condition.id, { value: e.target.value })}
              aria-label="Filter value"
              className="bg-terminal-black border border-terminal-green/40 text-terminal-green text-[11px] px-2 py-1 focus:outline-none focus:border-terminal-green cursor-pointer hover:border-terminal-green/70 transition-colors"
            >
              <option value="true" className="bg-[#0a0e27]">true</option>
              <option value="false" className="bg-[#0a0e27]">false</option>
            </select>
          ) : (
            <input
              type={fieldDef.type === "number" ? "number" : "text"}
              value={condition.value}
              onChange={(e) => onUpdate(condition.id, { value: e.target.value })}
              placeholder={isInOp ? "val1, val2, val3" : "value"}
              aria-label="Filter value"
              className="bg-terminal-black border border-terminal-green/40 text-terminal-green text-[11px] px-2 py-1 focus:outline-none focus:border-terminal-green min-w-[100px] placeholder:text-terminal-gray/50 hover:border-terminal-green/70 transition-colors"
            />
          )}
        </>
      )}

      {/* Type badge */}
      <span className="text-[9px] px-1 border border-terminal-gray/20 text-terminal-gray/60 uppercase">
        {fieldDef.type}
      </span>

      {/* Remove button */}
      {!isOnly && (
        <button
          type="button"
          onClick={() => onRemove(condition.id)}
          aria-label="Remove condition"
          className="ml-auto opacity-0 group-hover/row:opacity-100 transition-opacity text-terminal-danger hover:text-terminal-danger/80 p-0.5"
          data-testid="remove-condition-btn"
        >
          <Trash2 size={12} />
        </button>
      )}
    </div>
  )
}

// ── Group component (recursive) ────────────────────────────────────────────

interface FilterGroupNodeProps {
  group: FilterGroup
  depth: number
  isRoot: boolean
  onUpdate: (groupId: string, logic: LogicOp) => void
  onUpdateCondition: (id: string, patch: Partial<FilterCondition>) => void
  onRemoveNode: (id: string) => void
  onAddCondition: (groupId: string) => void
  onAddSubGroup: (groupId: string) => void
  totalNodes: number
}

function FilterGroupNode({
  group,
  depth,
  isRoot,
  onUpdate,
  onUpdateCondition,
  onRemoveNode,
  onAddCondition,
  onAddSubGroup,
  totalNodes,
}: FilterGroupNodeProps) {
  const [collapsed, setCollapsed] = React.useState(false)
  const depthColors = ["border-terminal-green/30", "border-terminal-cyan/30", "border-[#a855f7]/30", "border-terminal-warning/30"]
  const depthAccent = ["text-terminal-green", "text-terminal-cyan", "text-[#a855f7]", "text-terminal-warning"]
  const borderColor = depthColors[depth % depthColors.length]
  const accent = depthAccent[depth % depthAccent.length]

  return (
    <div
      className={`border ${borderColor} ${depth > 0 ? "ml-4" : ""}`}
      data-testid={isRoot ? "webhook-filter-root-group" : "webhook-filter-sub-group"}
    >
      {/* Group header */}
      <div className={`flex items-center gap-2 px-3 py-1.5 border-b ${borderColor} bg-terminal-green/3`}>
        {!isRoot && (
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className={`${accent} hover:opacity-70 transition-opacity`}
            aria-label={collapsed ? "Expand group" : "Collapse group"}
          >
            {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          </button>
        )}

        <span className={`text-[9px] tracking-widest ${accent}`}>
          {isRoot ? "[ROOT]" : `[GROUP_${depth}]`}
        </span>

        <span className="text-[9px] text-terminal-gray">MATCH</span>

        {(["AND", "OR"] as LogicOp[]).map((op) => (
          <button
            key={op}
            type="button"
            onClick={() => onUpdate(group.id, op)}
            aria-pressed={group.logic === op}
            data-testid={`logic-${op.toLowerCase()}-btn`}
            className={`text-[10px] px-2 py-0.5 border transition-all ${
              group.logic === op
                ? `border-current ${accent} bg-current/10`
                : "border-terminal-gray/30 text-terminal-gray hover:border-terminal-gray/60"
            }`}
          >
            {op}
          </button>
        ))}

        <span className={`text-[9px] text-terminal-gray ml-1`}>
          {group.children.length} rule{group.children.length !== 1 ? "s" : ""}
        </span>

        {/* Group actions */}
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => onAddCondition(group.id)}
            className="text-[9px] px-2 py-0.5 border border-terminal-green/30 text-terminal-green hover:border-terminal-green hover:bg-terminal-green/5 transition-colors flex items-center gap-1"
            data-testid="add-condition-btn"
          >
            <Plus size={10} /> CONDITION
          </button>
          <button
            type="button"
            onClick={() => onAddSubGroup(group.id)}
            className="text-[9px] px-2 py-0.5 border border-terminal-cyan/30 text-terminal-cyan hover:border-terminal-cyan hover:bg-terminal-cyan/5 transition-colors flex items-center gap-1"
            data-testid="add-group-btn"
          >
            <Layers size={10} /> GROUP
          </button>
          {!isRoot && totalNodes > 1 && (
            <button
              type="button"
              onClick={() => onRemoveNode(group.id)}
              aria-label="Remove group"
              className="text-terminal-danger hover:text-terminal-danger/70 transition-colors p-0.5"
              data-testid="remove-group-btn"
            >
              <Trash2 size={11} />
            </button>
          )}
        </div>
      </div>

      {/* Group children */}
      {!collapsed && (
        <div className="p-2 space-y-1.5">
          {group.children.length === 0 ? (
            <div className="text-[10px] text-terminal-gray/50 text-center py-2">
              No conditions — add one above
            </div>
          ) : (
            group.children.map((child, idx) => (
              <div key={child.id}>
                {idx > 0 && (
                  <div className={`text-[9px] ${accent} px-2 py-0.5 my-1 font-bold`}>
                    {group.logic}
                  </div>
                )}
                {child.kind === "condition" ? (
                  <ConditionRow
                    condition={child}
                    depth={depth}
                    isOnly={group.children.length === 1 && isRoot}
                    onUpdate={onUpdateCondition}
                    onRemove={onRemoveNode}
                  />
                ) : (
                  <FilterGroupNode
                    group={child}
                    depth={depth + 1}
                    isRoot={false}
                    onUpdate={onUpdate}
                    onUpdateCondition={onUpdateCondition}
                    onRemoveNode={onRemoveNode}
                    onAddCondition={onAddCondition}
                    onAddSubGroup={onAddSubGroup}
                    totalNodes={totalNodes}
                  />
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────

export interface WebhookFilterExpressionBuilderProps {
  value?: FilterExpression
  onChange: (expr: FilterExpression) => void
  /** Called when user explicitly applies/saves */
  onApply?: (expr: FilterExpression, serialized: string) => void
  className?: string
}

export function WebhookFilterExpressionBuilder({
  value,
  onChange,
  onApply,
  className = "",
}: WebhookFilterExpressionBuilderProps) {
  const [expr, setExpr] = React.useState<FilterExpression>(value ?? emptyExpression())
  const [previewExpanded, setPreviewExpanded] = React.useState(true)

  // Sync with external value
  React.useEffect(() => {
    if (value) setExpr(value)
  }, [value])

  const update = (next: FilterExpression) => {
    setExpr(next)
    onChange(next)
  }

  const serialized = React.useMemo(() => serializeExpression(expr), [expr])

  const countNodes = (group: FilterGroup): number => {
    return group.children.reduce((acc, child) => {
      if (child.kind === "group") return acc + countNodes(child)
      return acc + 1
    }, 0)
  }

  // ── Mutation handlers ──────────────────────────────────────────────────

  const handleUpdateGroupLogic = (groupId: string, logic: LogicOp) => {
    const updatedRoot = updateNodeInGroup(expr.root, groupId, (node) => {
      if (node.kind === "group") return { ...node, logic }
      return node
    }) as FilterGroup
    // Special case: root itself
    const newRoot = expr.root.id === groupId ? { ...expr.root, logic } : updatedRoot
    update({ root: newRoot })
  }

  const handleUpdateCondition = (id: string, patch: Partial<FilterCondition>) => {
    const newRoot = updateNodeInGroup(expr.root, id, (node) => {
      if (node.kind === "condition") return { ...node, ...patch }
      return node
    }) as FilterGroup
    update({ root: newRoot })
  }

  const handleRemoveNode = (id: string) => {
    const newRoot = removeNodeFromGroup(expr.root, id)
    update({ root: newRoot })
  }

  const handleAddCondition = (groupId: string) => {
    const cond = defaultCondition()
    const newRoot = addNodeToGroup(expr.root, groupId, cond)
    update({ root: newRoot })
  }

  const handleAddSubGroup = (groupId: string) => {
    const subGroup = defaultGroup()
    const newRoot = addNodeToGroup(expr.root, groupId, subGroup)
    update({ root: newRoot })
  }

  const handleReset = () => {
    const fresh = emptyExpression()
    update(fresh)
  }

  const totalNodes = countNodes(expr.root)

  return (
    <div
      className={`font-terminal-mono text-[11px] space-y-2 ${className}`}
      role="group"
      aria-label="Webhook filter expression builder"
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[9px] text-terminal-gray tracking-widest">
          {totalNodes} rule{totalNodes !== 1 ? "s" : ""} defined
        </span>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={handleReset}
            className="text-[9px] px-2 py-0.5 border border-terminal-danger/30 text-terminal-danger hover:border-terminal-danger hover:bg-terminal-danger/5 transition-colors"
            data-testid="reset-expression-btn"
          >
            RESET
          </button>
          {onApply && (
            <button
              type="button"
              onClick={() => onApply(expr, serialized)}
              className="text-[9px] px-2 py-0.5 border border-terminal-green/60 text-terminal-green hover:bg-terminal-green/10 transition-colors"
              data-testid="apply-expression-btn"
            >
              APPLY_FILTER
            </button>
          )}
        </div>
      </div>

      {/* Recursive tree */}
      <FilterGroupNode
        group={expr.root}
        depth={0}
        isRoot={true}
        onUpdate={handleUpdateGroupLogic}
        onUpdateCondition={handleUpdateCondition}
        onRemoveNode={handleRemoveNode}
        onAddCondition={handleAddCondition}
        onAddSubGroup={handleAddSubGroup}
        totalNodes={totalNodes}
      />

      {/* Expression preview */}
      <div className="border border-terminal-green/20 bg-terminal-green/3">
        <button
          type="button"
          onClick={() => setPreviewExpanded((p) => !p)}
          className="w-full flex items-center justify-between px-3 py-1.5 text-[9px] text-terminal-gray hover:text-terminal-green transition-colors"
          aria-expanded={previewExpanded}
          aria-controls="filter-expression-preview"
        >
          <span className="tracking-widest">EXPRESSION_PREVIEW</span>
          {previewExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </button>
        {previewExpanded && (
          <div
            id="filter-expression-preview"
            className="px-3 py-2 border-t border-terminal-green/10 text-terminal-cyan text-[10px] break-all leading-relaxed"
            data-testid="filter-expression-preview"
            aria-live="polite"
          >
            {serialized || "(empty expression)"}
          </div>
        )}
      </div>
    </div>
  )
}
