"use client";

import * as React from "react";
import { Button } from "@/components/terminal/Button";

interface ContractEmptyStateProps {
  onRegister: () => void;
}

/**
 * Shown inside the TRACKED_CONTRACTS card when the user has no contracts yet.
 * Renders an animated SVG icon, a friendly message, and a CTA button.
 * Fully responsive — stacks gracefully on small screens.
 */
export function ContractEmptyState({ onRegister }: ContractEmptyStateProps) {
  return (
    <div
      className="
        flex flex-col items-center justify-center gap-6
        py-16 px-4 sm:py-20
        font-terminal-mono
      "
      role="status"
      aria-label="No contracts registered"
    >
      {/* ── Animated terminal-style icon ── */}
      <div className="relative flex items-center justify-center">
        {/* Outer pulsing ring */}
        <span
          className="
            absolute inline-flex h-24 w-24 rounded-full
            border border-terminal-green/20
            animate-ping
          "
          aria-hidden="true"
        />
        {/* Static ring */}
        <span
          className="
            relative inline-flex items-center justify-center
            h-20 w-20 rounded-full
            border border-terminal-green/30
            bg-terminal-green/5
          "
          aria-hidden="true"
        >
          {/* Contract / file-code SVG icon */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-9 w-9 text-terminal-green"
            aria-hidden="true"
          >
            {/* Document outline */}
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            {/* Code lines */}
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="12" y2="17" />
            {/* Bracket hints */}
            <polyline points="10 9 8 11 10 13" />
          </svg>
        </span>
      </div>

      {/* ── Copy ── */}
      <div className="text-center space-y-2 max-w-sm">
        <p className="text-terminal-green text-lg tracking-widest uppercase">
          No contracts found
        </p>
        <p className="text-terminal-gray text-sm leading-relaxed">
          You haven&apos;t registered any Soroban contracts yet.
          <br className="hidden sm:block" />
          Register a contract to start indexing events.
        </p>
      </div>

      {/* ── Horizontal dashed separator ── */}
      <div
        className="w-full max-w-xs border-t border-dashed border-terminal-green/20"
        aria-hidden="true"
      />

      {/* ── CTA ── */}
      <Button
        id="empty-state-register-contract"
        variant="primary"
        size="lg"
        onClick={onRegister}
        aria-label="Register your first contract"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-4 w-4"
          aria-hidden="true"
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        Register Contract
      </Button>

      {/* ── Subtle hint ── */}
      <p className="text-terminal-gray/50 text-xs tracking-wider">
        $ soroscan contracts register --id &lt;CONTRACT_ID&gt;
      </p>
    </div>
  );
}
