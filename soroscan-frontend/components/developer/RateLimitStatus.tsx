"use client";

/**
 * RateLimitStatus — Displays current API rate limit quota with real-time updates.
 * Polls the rate limit headers from a lightweight probe endpoint.
 */

import * as React from "react";
import { Activity, RefreshCcw, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------- Types ----------

export interface RateLimitInfo {
  limit: number;
  remaining: number;
  resetAt: Date;
  plan: string;
}

interface UsageBar {
  label: string;
  used: number;
  total: number;
  color: string;
}

// ---------- Helpers ----------

function formatCountdown(resetAt: Date): string {
  const diff = Math.max(0, resetAt.getTime() - Date.now());
  const minutes = Math.floor(diff / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function getUsageColor(remaining: number, limit: number): string {
  const pct = remaining / limit;
  if (pct > 0.5) return "bg-terminal-green";
  if (pct > 0.2) return "bg-terminal-warning";
  return "bg-terminal-danger";
}

function getStatusText(remaining: number, limit: number): { text: string; className: string } {
  const pct = remaining / limit;
  if (pct > 0.5) return { text: "HEALTHY", className: "text-terminal-green" };
  if (pct > 0.2) return { text: "MODERATE", className: "text-terminal-warning" };
  if (pct > 0) return { text: "LOW", className: "text-terminal-danger" };
  return { text: "EXHAUSTED", className: "text-terminal-danger" };
}

// ---------- Mock data for when backend isn't available ----------

function getMockRateLimit(): RateLimitInfo {
  const resetAt = new Date(Date.now() + 35 * 60 * 1000); // 35 min from now
  return {
    limit: 1000,
    remaining: 743,
    resetAt,
    plan: "free",
  };
}

const PLAN_LIMITS: Record<string, { requests: number; webhooks: number; contracts: number }> = {
  free: { requests: 1000, webhooks: 3, contracts: 5 },
  pro: { requests: 10000, webhooks: 25, contracts: 50 },
  enterprise: { requests: 100000, webhooks: 200, contracts: 500 },
};

// ---------- Main Component ----------

interface RateLimitStatusProps {
  /** Polling interval in milliseconds (default: 30 seconds) */
  pollIntervalMs?: number;
  /** Mock data to use instead of fetching */
  mockData?: RateLimitInfo;
  className?: string;
}

export function RateLimitStatus({
  pollIntervalMs = 30_000,
  mockData,
  className,
}: RateLimitStatusProps) {
  const [info, setInfo] = React.useState<RateLimitInfo>(mockData ?? getMockRateLimit());
  const [countdown, setCountdown] = React.useState(() => formatCountdown(info.resetAt));
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = React.useState(new Date());

  // Probe endpoint for rate limit headers
  const fetchRateLimits = React.useCallback(async () => {
    if (mockData) return; // use provided mock data
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/dev/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/events/?limit=1`,
          method: "GET",
          headers: {},
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json() as { headers?: Record<string, string> };
      const h = data.headers ?? {};
      const limit = parseInt(h["x-ratelimit-limit"] ?? "1000", 10);
      const remaining = parseInt(h["x-ratelimit-remaining"] ?? "0", 10);
      const resetTs = parseInt(h["x-ratelimit-reset"] ?? "0", 10);
      const plan = h["x-soroscan-plan"] ?? "free";
      setInfo({
        limit: Number.isNaN(limit) ? 1000 : limit,
        remaining: Number.isNaN(remaining) ? 0 : remaining,
        resetAt: resetTs ? new Date(resetTs * 1000) : new Date(Date.now() + 3600_000),
        plan,
      });
      setLastRefreshed(new Date());
    } catch {
      setError("Unable to fetch rate limits — showing cached data.");
    } finally {
      setLoading(false);
    }
  }, [mockData]);

  // Initial fetch + polling
  React.useEffect(() => {
    void fetchRateLimits();
    const intervalId = window.setInterval(() => void fetchRateLimits(), pollIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [fetchRateLimits, pollIntervalMs]);

  // Countdown timer (updates every second)
  React.useEffect(() => {
    const timerId = window.setInterval(() => {
      setCountdown(formatCountdown(info.resetAt));
    }, 1000);
    return () => window.clearInterval(timerId);
  }, [info.resetAt]);

  const used = info.limit - info.remaining;
  const usagePct = Math.min(100, (used / info.limit) * 100);
  const planLimits = PLAN_LIMITS[info.plan] ?? PLAN_LIMITS.free;
  const status = getStatusText(info.remaining, info.limit);

  const usageBars: UsageBar[] = [
    {
      label: "API Requests",
      used,
      total: info.limit,
      color: getUsageColor(info.remaining, info.limit),
    },
    {
      label: "Webhooks",
      used: Math.min(2, planLimits.webhooks),
      total: planLimits.webhooks,
      color: "bg-terminal-cyan",
    },
    {
      label: "Contracts",
      used: Math.min(3, planLimits.contracts),
      total: planLimits.contracts,
      color: "bg-terminal-info",
    },
  ];

  return (
    <div
      className={cn("border border-terminal-green/20", className)}
      data-testid="rate-limit-status"
      aria-live="polite"
      aria-label="API rate limit status"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-terminal-green/20 bg-terminal-black/50">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-terminal-green" aria-hidden="true" />
          <div>
            <div className="text-[10px] text-terminal-cyan tracking-widest">[RATE_LIMIT]</div>
            <h2 className="text-sm font-bold text-terminal-green">API Quota Status</h2>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={cn("text-xs font-bold uppercase tracking-widest", status.className)}>
            {status.text}
          </span>
          <button
            type="button"
            onClick={() => void fetchRateLimits()}
            disabled={loading}
            aria-label="Refresh rate limit data"
            className="text-terminal-gray hover:text-terminal-cyan transition-colors disabled:opacity-50"
          >
            <RefreshCcw
              size={14}
              className={cn(loading && "animate-spin")}
              aria-hidden="true"
            />
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-terminal-warning/20 text-xs text-terminal-warning">
          <AlertTriangle size={12} aria-hidden="true" />
          {error}
        </div>
      )}

      {/* Main stats */}
      <div className="p-4 space-y-5">
        {/* Hourly window */}
        <div className="space-y-2">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-terminal-gray">This hour</span>
            <span className="text-terminal-gray">
              Resets in{" "}
              <span className="text-terminal-cyan font-mono">{countdown}</span>
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-bold font-mono text-terminal-green">
              {info.remaining.toLocaleString()}
            </span>
            <span className="text-terminal-gray text-sm">
              / {info.limit.toLocaleString()} requests remaining
            </span>
          </div>
          <div className="relative h-3 bg-terminal-dark border border-terminal-green/20 overflow-hidden" role="progressbar" aria-valuenow={usagePct} aria-valuemin={0} aria-valuemax={100} aria-label="Request usage">
            <div
              className={cn("h-full transition-all duration-500", getUsageColor(info.remaining, info.limit))}
              style={{ width: `${usagePct}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-terminal-gray-muted">
            <span>{used.toLocaleString()} used</span>
            <span>{usagePct.toFixed(1)}% consumed</span>
          </div>
        </div>

        {/* Usage bars for each resource */}
        <div className="space-y-3 pt-2 border-t border-terminal-green/10">
          {usageBars.map((bar) => {
            const barPct = Math.min(100, (bar.used / bar.total) * 100);
            return (
              <div key={bar.label} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-terminal-gray">{bar.label}</span>
                  <span className="text-terminal-gray font-mono">
                    {bar.used} / {bar.total}
                  </span>
                </div>
                <div
                  className="h-1.5 bg-terminal-dark border border-terminal-green/10 overflow-hidden"
                  role="progressbar"
                  aria-valuenow={barPct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${bar.label} usage`}
                >
                  <div
                    className={cn("h-full transition-all duration-500", bar.color)}
                    style={{ width: `${barPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Plan badge */}
        <div className="pt-2 border-t border-terminal-green/10 flex items-center justify-between text-xs">
          <span className="text-terminal-gray">Current plan</span>
          <span className="uppercase tracking-widest font-bold text-terminal-cyan border border-terminal-cyan/30 px-2 py-0.5">
            {info.plan}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-terminal-green/10 text-[10px] text-terminal-gray-muted">
        Last refreshed: {lastRefreshed.toLocaleTimeString()} · Auto-refreshes every{" "}
        {pollIntervalMs / 1000}s
      </div>
    </div>
  );
}
