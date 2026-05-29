import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ExportProgressModal from '../ExportProgressModal';

const baseProps = {
  open: true,
  progress: 50,
};

describe('ExportProgressModal', () => {
  // --- Visibility ---
  it('renders modal when open=true', () => {
    render(<ExportProgressModal {...baseProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('renders nothing when open=false', () => {
    render(<ExportProgressModal open={false} progress={50} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders backdrop when open', () => {
    render(<ExportProgressModal {...baseProps} />);
    expect(screen.getByTestId('modal-backdrop')).toBeInTheDocument();
  });

  // --- Progress bar ---
  it('renders a progress bar', () => {
    render(<ExportProgressModal {...baseProps} />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('shows correct progress percentage', () => {
    render(<ExportProgressModal {...baseProps} progress={72} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '72');
  });

  it('shows 100% progress when complete', () => {
    render(<ExportProgressModal open={true} progress={100} status="complete" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });

  // --- Estimated time ---
  it('shows estimated time while exporting', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" estimatedSeconds={90} />);
    expect(screen.getByTestId('estimated-time')).toHaveTextContent('~1m 30s remaining');
  });

  it('hides estimated time when not provided', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" />);
    expect(screen.queryByTestId('estimated-time')).not.toBeInTheDocument();
  });

  it('hides estimated time when status is complete', () => {
    render(<ExportProgressModal open={true} progress={100} status="complete" estimatedSeconds={10} />);
    expect(screen.queryByTestId('estimated-time')).not.toBeInTheDocument();
  });

  it('formats seconds-only time correctly', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" estimatedSeconds={45} />);
    expect(screen.getByTestId('estimated-time')).toHaveTextContent('~45s remaining');
  });

  it('formats whole-minute time correctly', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" estimatedSeconds={120} />);
    expect(screen.getByTestId('estimated-time')).toHaveTextContent('~2m remaining');
  });

  // --- Filename ---
  it('displays filename when provided', () => {
    render(<ExportProgressModal {...baseProps} filename="events_export.csv" />);
    expect(screen.getByTestId('export-filename')).toHaveTextContent('events_export.csv');
  });

  it('does not render filename element when omitted', () => {
    render(<ExportProgressModal {...baseProps} />);
    expect(screen.queryByTestId('export-filename')).not.toBeInTheDocument();
  });

  // --- Cancel ---
  it('shows cancel button while exporting', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" />);
    expect(screen.getByTestId('cancel-button')).toBeInTheDocument();
  });

  it('calls onCancel when cancel button is clicked', () => {
    const handleCancel = jest.fn();
    render(<ExportProgressModal {...baseProps} status="exporting" onCancel={handleCancel} />);
    fireEvent.click(screen.getByTestId('cancel-button'));
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it('hides cancel button when complete', () => {
    render(<ExportProgressModal open={true} progress={100} status="complete" />);
    expect(screen.queryByTestId('cancel-button')).not.toBeInTheDocument();
  });

  it('hides cancel button when cancelled', () => {
    render(<ExportProgressModal open={true} progress={40} status="cancelled" />);
    expect(screen.queryByTestId('cancel-button')).not.toBeInTheDocument();
  });

  // --- Status text ---
  it('shows "Exporting…" status text while exporting', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" />);
    expect(screen.getByTestId('export-status-text')).toHaveTextContent('Exporting…');
  });

  it('shows "Export complete" status text when complete', () => {
    render(<ExportProgressModal open={true} progress={100} status="complete" />);
    expect(screen.getByTestId('export-status-text')).toHaveTextContent('Export complete');
  });

  it('shows "Export cancelled" status text when cancelled', () => {
    render(<ExportProgressModal open={true} progress={40} status="cancelled" />);
    expect(screen.getByTestId('export-status-text')).toHaveTextContent('Export cancelled');
  });

  it('shows "Export failed" status text on error', () => {
    render(<ExportProgressModal open={true} progress={30} status="error" />);
    expect(screen.getByTestId('export-status-text')).toHaveTextContent('Export failed');
  });

  // --- Download ---
  it('shows download button when complete with downloadUrl', () => {
    render(
      <ExportProgressModal
        open={true}
        progress={100}
        status="complete"
        downloadUrl="/exports/file.csv"
      />
    );
    expect(screen.getByTestId('download-button')).toBeInTheDocument();
  });

  it('download button has correct href', () => {
    render(
      <ExportProgressModal
        open={true}
        progress={100}
        status="complete"
        downloadUrl="/exports/file.csv"
        filename="file.csv"
      />
    );
    const btn = screen.getByTestId('download-button');
    expect(btn).toHaveAttribute('href', '/exports/file.csv');
    expect(btn).toHaveAttribute('download', 'file.csv');
  });

  it('hidden anchor has correct download attributes', () => {
    render(
      <ExportProgressModal
        open={true}
        progress={100}
        status="complete"
        downloadUrl="/exports/file.csv"
        filename="file.csv"
      />
    );
    const anchor = screen.getByTestId('download-anchor');
    expect(anchor).toHaveAttribute('href', '/exports/file.csv');
    expect(anchor).toHaveAttribute('download', 'file.csv');
  });

  it('does not show download button when no downloadUrl', () => {
    render(<ExportProgressModal open={true} progress={100} status="complete" />);
    expect(screen.queryByTestId('download-button')).not.toBeInTheDocument();
  });

  // --- Close ---
  it('shows close button when complete', () => {
    render(<ExportProgressModal open={true} progress={100} status="complete" />);
    expect(screen.getByTestId('close-button')).toBeInTheDocument();
  });

  it('shows close button when cancelled', () => {
    render(<ExportProgressModal open={true} progress={40} status="cancelled" />);
    expect(screen.getByTestId('close-button')).toBeInTheDocument();
  });

  it('shows close button on error', () => {
    render(<ExportProgressModal open={true} progress={30} status="error" />);
    expect(screen.getByTestId('close-button')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = jest.fn();
    render(
      <ExportProgressModal
        open={true}
        progress={100}
        status="complete"
        onClose={handleClose}
      />
    );
    fireEvent.click(screen.getByTestId('close-button'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when header × button is clicked', () => {
    const handleClose = jest.fn();
    render(
      <ExportProgressModal
        open={true}
        progress={100}
        status="complete"
        onClose={handleClose}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('does not show close button while exporting', () => {
    render(<ExportProgressModal {...baseProps} status="exporting" />);
    expect(screen.queryByTestId('close-button')).not.toBeInTheDocument();
  });

  // --- Accessibility ---
  it('dialog has aria-modal=true', () => {
    render(<ExportProgressModal {...baseProps} />);
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
  });

  it('dialog is labelled by title', () => {
    render(<ExportProgressModal {...baseProps} />);
    const dialog = screen.getByRole('dialog');
    const titleId = dialog.getAttribute('aria-labelledby');
    expect(titleId).toBeTruthy();
    expect(document.getElementById(titleId!)).toBeInTheDocument();
  });

  // --- Custom className ---
  it('applies custom className to panel', () => {
    render(<ExportProgressModal {...baseProps} className="my-modal" />);
    expect(screen.getByTestId('export-modal-panel')).toHaveClass('my-modal');
  });
});
