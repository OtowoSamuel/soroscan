"use client"

import * as React from "react"
import { ArrowLeft, Copy, Check, FlaskConical } from "lucide-react"
import Link from "next/link"
import { Navbar } from "@/components/terminal/landing/Navbar"
import { Footer } from "@/components/terminal/landing/Footer"
import {
  WebhookFilterExpressionBuilder,
  emptyExpression,
  serializeExpression,
  type FilterExpression,
} from "@/components/ui/WebhookFilterExpressionBuilder"
import { FilterExpressionTester } from "@/components/ui/FilterExpressionTester"

export default function FilterBuilderPage() {
  const [expr, setExpr] = React.useState<FilterExpression>(emptyExpression())
  const [activeTab, setActiveTab] = React.useState<"build" | "test">("build")
  const [copied, setCopied] = React.useState(false)

  const serialized = serializeExpression(expr)

  const handleCopy = () => {
    navigator.clipboard.writeText(serialized).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="min-h-screen font-terminal-mono selection:bg-terminal-green selection:text-terminal-black">
      <Navbar />

      <main className="container mx-auto px-6 md:px-8 py-10 md:py-14 space-y-8 max-w-5xl">

        {/* Breadcrumb */}
        <Link
          href="/webhooks"
          className="inline-flex items-center gap-2 text-[10px] text-terminal-gray hover:text-terminal-green transition-colors tracking-widest"
        >
          <ArrowLeft size={11} /> BACK_TO_WEBHOOKS
        </Link>

        {/* Header */}
        <div>
          <div className="text-[10px] text-terminal-cyan tracking-widest mb-1">[FILTER_EXPRESSION_BUILDER]</div>
          <h1 className="text-3xl md:text-4xl font-bold text-terminal-green">
            FILTER BUILDER
          </h1>
          <p className="text-terminal-gray text-xs mt-2 max-w-xl">
            Construct complex filter expressions using nested AND/OR logic. Test your expression against
            a sample event payload before attaching it to a webhook subscription.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* Builder panel — takes 3/5 width on large screens */}
          <div className="lg:col-span-3 space-y-4">
            {/* Tab bar */}
            <div className="flex border-b border-terminal-green/20" role="tablist">
              {([
                { id: "build", label: "BUILD_EXPRESSION" },
                { id: "test",  label: "TEST_EXPRESSION", icon: <FlaskConical size={11} /> },
              ] as const).map((tab) => (
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
                  data-testid={`page-tab-${tab.id}`}
                >
                  {"icon" in tab && tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            <div role="tabpanel">
              {activeTab === "build" ? (
                <WebhookFilterExpressionBuilder
                  value={expr}
                  onChange={setExpr}
                />
              ) : (
                <FilterExpressionTester expression={expr} />
              )}
            </div>
          </div>

          {/* Sidebar — expression output + help */}
          <div className="lg:col-span-2 space-y-4">

            {/* Generated expression */}
            <div className="border border-terminal-green/30">
              <div className="flex items-center justify-between px-3 py-2 border-b border-terminal-green/20 bg-terminal-green/3">
                <span className="text-[9px] text-terminal-green tracking-widest">GENERATED_EXPRESSION</span>
                <button
                  type="button"
                  onClick={handleCopy}
                  disabled={!serialized}
                  aria-label="Copy expression to clipboard"
                  className="text-[9px] flex items-center gap-1 text-terminal-gray hover:text-terminal-green transition-colors disabled:opacity-40"
                  data-testid="copy-expression-btn"
                >
                  {copied ? <Check size={11} /> : <Copy size={11} />}
                  {copied ? "COPIED" : "COPY"}
                </button>
              </div>
              <pre
                className="px-3 py-3 text-[10px] text-terminal-cyan break-all whitespace-pre-wrap leading-relaxed min-h-[80px]"
                data-testid="page-expression-preview"
              >
                {serialized || "(empty)"}
              </pre>
            </div>

            {/* Quick reference */}
            <div className="border border-terminal-green/20 space-y-0">
              <div className="px-3 py-2 border-b border-terminal-green/20 bg-terminal-green/3">
                <span className="text-[9px] text-terminal-green tracking-widest">QUICK_REFERENCE</span>
              </div>
              <div className="px-3 py-3 space-y-3 text-[10px] text-terminal-gray">
                {[
                  { sym: "=",         desc: "Exact match" },
                  { sym: "!=",        desc: "Not equal" },
                  { sym: "~=",        desc: "Contains substring" },
                  { sym: "^=",        desc: "Starts with" },
                  { sym: "$=",        desc: "Ends with" },
                  { sym: "> / >=",    desc: "Greater than (numeric)" },
                  { sym: "< / <=",    desc: "Less than (numeric)" },
                  { sym: "IN [...]",  desc: "Matches any in list" },
                  { sym: "EXISTS()",  desc: "Field is present" },
                ].map((r) => (
                  <div key={r.sym} className="flex items-start gap-3">
                    <code className="text-terminal-cyan font-bold w-20 shrink-0">{r.sym}</code>
                    <span>{r.desc}</span>
                  </div>
                ))}

                <div className="border-t border-terminal-green/10 pt-3 space-y-1.5">
                  <div className="text-[9px] text-terminal-cyan tracking-wider">BOOLEAN_LOGIC</div>
                  <div className="flex gap-2">
                    <code className="text-terminal-green font-bold w-8 shrink-0">AND</code>
                    <span>All conditions must match</span>
                  </div>
                  <div className="flex gap-2">
                    <code className="text-terminal-cyan font-bold w-8 shrink-0">OR</code>
                    <span>At least one must match</span>
                  </div>
                  <div className="mt-1 text-terminal-gray/60">
                    Groups can be infinitely nested to build complex logic.
                  </div>
                </div>
              </div>
            </div>

            {/* Use expression CTA */}
            <Link
              href="/webhooks"
              className="flex items-center justify-center gap-2 w-full border border-terminal-green/40 text-terminal-green py-3 text-[11px] tracking-widest hover:bg-terminal-green/10 transition-colors"
              data-testid="use-expression-link"
            >
              USE IN WEBHOOK →
            </Link>

          </div>
        </div>
      </main>

      <div className="container mx-auto px-6 md:px-8 max-w-5xl pb-12">
        <Footer />
      </div>

      {/* Background grid */}
      <div className="fixed inset-0 pointer-events-none z-[-1] overflow-hidden opacity-20">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(0,255,65,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,65,0.03)_1px,transparent_1px)] bg-size-[40px_40px]" />
      </div>
    </div>
  )
}
