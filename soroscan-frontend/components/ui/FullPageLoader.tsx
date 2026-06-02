"use client";

import * as React from "react";

interface FullPageLoaderProps {
  isLoading: boolean;
  message?: string;
}

export function FullPageLoader({ isLoading, message = "Loading..." }: FullPageLoaderProps) {
  if (!isLoading) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-0 z-[9999] grid place-items-center bg-terminal-black/90 text-terminal-green"
    >
      <div className="flex flex-col items-center justify-center gap-4 rounded border border-terminal-green/30 bg-terminal-black/95 p-6 shadow-glow-green/30">
        <div className="h-16 w-16 rounded-full border-4 border-terminal-green/10 border-t-terminal-green animate-spin" />
        <span className="text-sm font-terminal-mono text-terminal-green/80">{message}</span>
      </div>
      <span className="sr-only">{message}</span>
    </div>
  );
}
