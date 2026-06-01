"use client"

import * as React from "react"
import { FlaskConical, Wand2 } from "lucide-react"
import { Modal } from "@/components/terminal/Modal"
import {
  WebhookFilterExpressionBuilder,
  emptyExpression,
  serializeExpression,
  type FilterExpression,
} from "@/components/ui/WebhookFilterExpressionBuilder"
import { FilterExpressionTester } from "@/components/ui/FilterExpressionTester"

export interface FilterBuilderModalProps {
  isOpen: boolean
  onClose: () => void
  /** Called when the user confirms/saves the filter expression string */
  onSave: (expressionString: string, expression: FilterExpression) => void
  /** Pre-populate with an existing expression */
  initialExpression?: FilterExpression
}

type Tab = "build" | "test"

export function FilterBuilderModal({
  isOpen,
  onClose,
  onSave,
  initialExpression,
}: FilterBuilderModalProps) {
  const [expr, setExpr] = React.useState<FilterExpression>(initialExpression ?? emptyExpression())
  const [activeTab, setActiveTab] = React.useState<Tab>("build")

  // Reset when modal re-opens
  React.useEffect(() => {
    if (isOpen) {
      setExpr(initialExpression ?? emptyExpression())
      setActiveTab("build")
    }
  }, [isOpen, initialExpression])

  const serialized = serializeExpression(expr)

  const handleSave = () => {
    onSave(serialized, expr)
    onClose()
  }

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "build", label: "BUILD", icon: <Wand2 size={11} /> },
    { id: "test",  label: "TEST",  icon: <FlaskConical size={11} /> },
  ]

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="FILTER_EXPRESSION_BUILDER">
      <div className="space-y-4 min-h-[400px]">
        {/* Tab bar */}
        <div className="flex border-b border-terminal-green/20" role="tablist">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2 text-[10px] tracking-widest border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-terminal-green text-terminal-green"
                  : "border-transparent text-terminal-gray hover:text-terminal-green/70"
              }`}
              data-testid={`tab-${tab.id}`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === "build" && (
          <WebhookFilterExpressionBuilder
            value={expr}
            onChange={setExpr}
          />
        )}
        {activeTab === "test" && (
          <FilterExpressionTester expression={expr} />
        )}

        {/* Footer actions */}
        <div className="flex gap-3 pt-2 border-t border-terminal-green/20">
          <button
            type="button"
            onClick={handleSave}
            className="flex-1 border border-terminal-green text-terminal-green py-2 text-[11px] tracking-widest hover:bg-terminal-green/10 transition-colors"
            data-testid="save-filter-btn"
          >
            SAVE_FILTER
          </button>
          <button
            type="button"
            onClick={onClose}
            className="border border-terminal-danger/40 text-terminal-danger px-4 py-2 text-[11px] hover:border-terminal-danger hover:bg-terminal-danger/5 transition-colors"
            data-testid="cancel-filter-btn"
          >
            CANCEL
          </button>
        </div>
      </div>
    </Modal>
  )
}
