"use client";

import * as React from "react";
import { Modal } from "@/components/terminal/Modal";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/terminal/Button";

export interface ExportEventsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExport: (format: string) => void;
  progress: number;
  isExporting: boolean;
}

export function ExportEventsModal({
  isOpen,
  onClose,
  onExport,
  progress,
  isExporting,
}: ExportEventsModalProps) {
  const [format, setFormat] = React.useState<"csv" | "json">("csv");

  const handleExport = React.useCallback(() => {
    onExport(format);
  }, [format, onExport]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="EXPORT_EVENTS">
      <div className="space-y-6">
        <div className="space-y-3">
          <p className="text-xs font-terminal-mono text-terminal-cyan uppercase tracking-wider">
            Format
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setFormat("csv")}
              className={`px-4 py-2 text-xs font-terminal-mono border transition-colors ${
                format === "csv"
                  ? "border-terminal-green text-terminal-green bg-terminal-green/10"
                  : "border-terminal-gray text-terminal-gray hover:border-terminal-green/50"
              }`}
            >
              CSV
            </button>
            <button
              type="button"
              onClick={() => setFormat("json")}
              className={`px-4 py-2 text-xs font-terminal-mono border transition-colors ${
                format === "json"
                  ? "border-terminal-green text-terminal-green bg-terminal-green/10"
                  : "border-terminal-gray text-terminal-gray hover:border-terminal-green/50"
              }`}
            >
              JSON
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-terminal-mono text-terminal-cyan uppercase tracking-wider">
            Progress
          </p>
          <Progress
            value={progress}
            max={100}
            variant="terminal"
            size="md"
            showLabel
          />
          <p className="text-[10px] font-terminal-mono text-terminal-gray">
            {progress.toFixed(0)}% complete
          </p>
        </div>

        {isExporting && (
          <div className="border border-terminal-green/30 bg-terminal-green/5 p-3">
            <p className="text-xs font-terminal-mono text-terminal-green animate-pulse">
              PROCESSING_EXPORT — Please do not close this window.
            </p>
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button variant="primary" size="sm" onClick={handleExport} disabled={isExporting}>
            {isExporting ? "EXPORTING..." : `EXPORT AS ${format.toUpperCase()}`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
