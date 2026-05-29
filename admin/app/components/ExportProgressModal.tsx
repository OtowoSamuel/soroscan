'use client';

import React, { useEffect, useRef, useCallback } from 'react';
import ProgressBar from './ProgressBar';

export type ExportStatus = 'idle' | 'exporting' | 'complete' | 'cancelled' | 'error';

export interface ExportProgressModalProps {
  /** Whether the modal is visible */
  open: boolean;
  /** Current export progress 0–100 */
  progress: number;
  /** Current status of the export */
  status?: ExportStatus;
  /** Filename that will be downloaded on completion */
  filename?: string;
  /** Estimated seconds remaining (omit to hide) */
  estimatedSeconds?: number;
  /** URL to trigger download when export is complete */
  downloadUrl?: string;
  /** Called when the user clicks Cancel */
  onCancel?: () => void;
  /** Called when the modal is closed after completion or cancellation */
  onClose?: () => void;
  /** Additional CSS classes for the modal panel */
  className?: string;
}

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

const ExportProgressModal: React.FC<ExportProgressModalProps> = ({
  open,
  progress,
  status = 'exporting',
  filename,
  estimatedSeconds,
  downloadUrl,
  onCancel,
  onClose,
  className = '',
}) => {
  const downloadTriggeredRef = useRef(false);
  const anchorRef = useRef<HTMLAnchorElement>(null);

  // Automatically trigger download when status flips to complete
  const triggerDownload = useCallback(() => {
    if (!downloadUrl || downloadTriggeredRef.current) return;
    downloadTriggeredRef.current = true;
    if (anchorRef.current) {
      anchorRef.current.click();
    }
  }, [downloadUrl]);

  useEffect(() => {
    if (status === 'complete') {
      triggerDownload();
    }
  }, [status, triggerDownload]);

  // Reset download guard when modal re-opens
  useEffect(() => {
    if (open) {
      downloadTriggeredRef.current = false;
    }
  }, [open]);

  if (!open) return null;

  const isComplete = status === 'complete';
  const isCancelled = status === 'cancelled';
  const isError = status === 'error';
  const isExporting = status === 'exporting';
  const isDone = isComplete || isCancelled || isError;

  const progressVariant = isComplete
    ? 'success'
    : isError
    ? 'danger'
    : 'primary';

  const statusText = isComplete
    ? 'Export complete'
    : isCancelled
    ? 'Export cancelled'
    : isError
    ? 'Export failed'
    : 'Exporting…';

  return (
    <>
      {/* Hidden anchor for programmatic download */}
      {downloadUrl && (
        <a
          ref={anchorRef}
          href={downloadUrl}
          download={filename}
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
          data-testid="download-anchor"
        />
      )}

      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        aria-hidden="true"
        data-testid="modal-backdrop"
      />

      {/* Modal panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-modal-title"
        className={`
          fixed inset-0 z-50 flex items-center justify-center p-4
        `.trim()}
      >
        <div
          className={`
            w-full max-w-md bg-white rounded-lg shadow-xl
            border border-gray-200 p-6 flex flex-col gap-4
            ${className}
          `.trim().replace(/\s+/g, ' ')}
          data-testid="export-modal-panel"
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <h2
              id="export-modal-title"
              className="text-base font-semibold text-gray-900"
            >
              {isComplete ? 'Download Ready' : 'Exporting Data'}
            </h2>

            {isDone && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="text-gray-400 hover:text-gray-600 transition-colors rounded"
              >
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4" aria-hidden="true">
                  <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            )}
          </div>

          {/* Filename */}
          {filename && (
            <p className="text-sm text-gray-500 truncate" data-testid="export-filename">
              {filename}
            </p>
          )}

          {/* Progress bar */}
          <ProgressBar
            value={progress}
            variant={progressVariant}
            showPercentage
            animated={isExporting}
          />

          {/* Status row */}
          <div className="flex items-center justify-between text-sm">
            <span
              className={`font-medium ${
                isComplete
                  ? 'text-green-600'
                  : isError
                  ? 'text-red-600'
                  : isCancelled
                  ? 'text-gray-500'
                  : 'text-blue-600'
              }`}
              data-testid="export-status-text"
            >
              {statusText}
            </span>

            {isExporting && estimatedSeconds !== undefined && (
              <span className="text-gray-400" data-testid="estimated-time">
                ~{formatTime(estimatedSeconds)} remaining
              </span>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            {isExporting && (
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                data-testid="cancel-button"
              >
                Cancel
              </button>
            )}

            {isComplete && downloadUrl && (
              <a
                href={downloadUrl}
                download={filename}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
                data-testid="download-button"
              >
                Download
              </a>
            )}

            {isDone && (
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                data-testid="close-button"
              >
                Close
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default ExportProgressModal;
