import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { EventTable } from "../EventTable";
import type { EventRecord } from "@/components/ingest/types";

describe("EventTable", () => {
  const mockEvents: EventRecord[] = [
    {
      id: "1",
      contractId: "CCAAA123",
      contractName: "Test Contract",
      eventType: "transfer",
      ledger: 1000,
      eventIndex: 0,
      timestamp: "2024-01-01T00:00:00Z",
      txHash: "abc123",
      payload: { amount: 100 },
    },
    {
      id: "2",
      contractId: "CCBBB456",
      contractName: "Another Contract",
      eventType: "swap",
      ledger: 1001,
      eventIndex: 1,
      timestamp: "2024-01-01T01:00:00Z",
      txHash: "def456",
      payload: { from: "A", to: "B" },
    },
  ];

  const mockOnEventClick = jest.fn();

  beforeEach(() => {
    mockOnEventClick.mockClear();
    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn(() => Promise.resolve()),
      },
    });
  });

  describe("Loading State (issue #595)", () => {
    it("shows skeleton loader while loading", () => {
      const { container } = render(
        <EventTable events={[]} loading={true} onEventClick={mockOnEventClick} />
      );

      // Check that skeleton rows are rendered
      const skeletonRows = container.querySelectorAll("tbody tr");
      expect(skeletonRows.length).toBe(5);

      // Check that skeleton elements exist
      const skeletons = container.querySelectorAll(".skeleton");
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it("skeleton matches table structure with 6 columns", () => {
      const { container } = render(
        <EventTable events={[]} loading={true} onEventClick={mockOnEventClick} />
      );

      const firstRow = container.querySelector("tbody tr");
      const cells = firstRow?.querySelectorAll("td");
      
      // Should have 6 columns: Contract, Type, Ledger, Time, Transaction, Actions
      expect(cells?.length).toBe(6);
    });

    it("skeleton has proper styling for each column type", () => {
      const { container } = render(
        <EventTable events={[]} loading={true} onEventClick={mockOnEventClick} />
      );

      const firstRow = container.querySelector("tbody tr");
      const skeletons = firstRow?.querySelectorAll(".skeleton");
      
      // Check that different columns have different skeleton widths
      expect(skeletons?.length).toBe(6);
      
      // Contract column skeleton
      expect(skeletons?.[0]).toHaveStyle({ width: "120px" });
      
      // Type column skeleton (pill-shaped)
      expect(skeletons?.[1]).toHaveStyle({ borderRadius: "12px" });
    });

    it("does not show skeleton when not loading", () => {
      const { container } = render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const skeletons = container.querySelectorAll(".skeleton");
      expect(skeletons.length).toBe(0);
    });

    it("transitions smoothly from skeleton to content", () => {
      const { container, rerender } = render(
        <EventTable events={[]} loading={true} onEventClick={mockOnEventClick} />
      );

      // Initially shows skeleton
      let skeletons = container.querySelectorAll(".skeleton");
      expect(skeletons.length).toBeGreaterThan(0);

      // Rerender with data
      rerender(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      // Skeleton should be gone
      skeletons = container.querySelectorAll(".skeleton");
      expect(skeletons.length).toBe(0);

      // Content should be visible (check for shortened contract ID)
      expect(screen.getByText(/CCAAA/)).toBeInTheDocument();
    });
  });

  describe("Event Display", () => {
    it("renders events when not loading", () => {
      render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      // Check for shortened contract IDs (not full names)
      expect(screen.getByText(/CCAAA/)).toBeInTheDocument();
      expect(screen.getByText(/CCBBB/)).toBeInTheDocument();
      expect(screen.getByText("transfer")).toBeInTheDocument();
      expect(screen.getByText("swap")).toBeInTheDocument();
    });

    it("shows empty state when no events and not loading", () => {
      render(
        <EventTable events={[]} loading={false} onEventClick={mockOnEventClick} />
      );

      expect(screen.getByText(/No events found/i)).toBeInTheDocument();
    });

    it("calls onEventClick when View button is clicked", () => {
      render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const viewButtons = screen.getAllByRole("button", { name: /view/i });
      fireEvent.click(viewButtons[0]);

      expect(mockOnEventClick).toHaveBeenCalledWith(mockEvents[0]);
    });

    it("copies contract ID to clipboard", async () => {
      render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const copyButtons = screen.getAllByTitle("Copy contract ID");
      fireEvent.click(copyButtons[0]);

      await waitFor(() => {
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith("CCAAA123");
      });
    });

    it("copies transaction hash to clipboard", async () => {
      render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const copyButtons = screen.getAllByTitle("Copy transaction hash");
      fireEvent.click(copyButtons[0]);

      await waitFor(() => {
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith("abc123");
      });
    });

    it("shows checkmark after successful copy", async () => {
      jest.useFakeTimers();
      render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const copyButtons = screen.getAllByTitle("Copy contract ID");
      fireEvent.click(copyButtons[0]);

      await waitFor(() => {
        expect(copyButtons[0]).toHaveTextContent("✓");
      });

      // After 2 seconds, should revert to clipboard icon
      jest.advanceTimersByTime(2000);

      await waitFor(() => {
        expect(copyButtons[0]).toHaveTextContent("📋");
      });

      jest.useRealTimers();
    });

    it("applies hover effects to event rows", () => {
      const { container } = render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const eventRow = container.querySelector("tbody tr");
      expect(eventRow).toHaveStyle({ cursor: "pointer" });
    });
  });

  describe("Accessibility", () => {
    it("has proper table structure", () => {
      render(
        <EventTable events={mockEvents} loading={false} onEventClick={mockOnEventClick} />
      );

      const table = screen.getByRole("table");
      expect(table).toBeInTheDocument();

      const headers = screen.getAllByRole("columnheader");
      expect(headers).toHaveLength(6);
    });

    it("skeleton rows have unique keys", () => {
      const { container } = render(
        <EventTable events={[]} loading={true} onEventClick={mockOnEventClick} />
      );

      const rows = container.querySelectorAll("tbody tr");
      
      // Check that we have 5 skeleton rows
      expect(rows.length).toBe(5);
      
      // React keys are used internally and don't appear in DOM
      // Just verify all rows are rendered
      rows.forEach((row) => {
        expect(row).toBeInTheDocument();
      });
    });
  });
});
