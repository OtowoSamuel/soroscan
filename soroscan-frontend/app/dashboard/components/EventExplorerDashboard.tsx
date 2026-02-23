"use client";

import { useState, useEffect, useCallback } from "react";
import { EventTable } from "./EventTable";
import { FilterBar } from "./FilterBar";
import { EventDetailModal } from "./EventDetailModal";
import { PaginationControls } from "./PaginationControls";
import { fetchAllContracts, fetchExplorerEvents } from "@/components/ingest/graphql";
import type { EventRecord } from "@/components/ingest/types";
import styles from "@/components/ingest/ingest-terminal.module.css";
import { useToast } from "@/context/ToastContext";

const PAGE_SIZE = 20;

interface Filters {
  contractId: string;
  eventType: string;
  since: string;
  until: string;
  searchQuery: string;
}

export function EventExplorerDashboard() {
  const { showToast } = useToast();
  const [contracts, setContracts] = useState<Array<{ contractId: string; name: string }>>([]);
  const [filters, setFilters] = useState<Filters>({
    contractId: "",
    eventType: "",
    since: "",
    until: "",
    searchQuery: "",
  });
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [filteredEvents, setFilteredEvents] = useState<EventRecord[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);
  const [totalCount, setTotalCount] = useState(0);

  // Load contracts on mount
  useEffect(() => {
    const loadContracts = async () => {
      try {
        const contractList = await fetchAllContracts();
        setContracts(contractList);
      } catch (err) {
        console.error("Failed to load contracts:", err);
      }
    };
    loadContracts();
  }, []);

  // Load events when filters or page changes
  useEffect(() => {
    const loadEvents = async () => {
      // Require contract selection
      if (!filters.contractId) {
        setEvents([]);
        setFilteredEvents([]);
        setHasNext(false);
        setLoading(false);
        setError(null);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const offset = (currentPage - 1) * PAGE_SIZE;
        const result = await fetchExplorerEvents({
          contractId: filters.contractId,
          eventType: filters.eventType || null,
          limit: PAGE_SIZE + 1,
          offset,
          since: filters.since || null,
          until: filters.until || null,
        });

        const nextExists = result.length > PAGE_SIZE;
        const visibleEvents = nextExists ? result.slice(0, PAGE_SIZE) : result;
        
        setEvents(visibleEvents);
        setHasNext(nextExists);
        setTotalCount(offset + result.length);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load events");
        setEvents([]);
        setHasNext(false);
      } finally {
        setLoading(false);
      }
    };

    loadEvents();
  }, [filters.contractId, filters.eventType, filters.since, filters.until, currentPage]);

  // Apply search filter client-side
  useEffect(() => {
    if (!filters.searchQuery.trim()) {
      setFilteredEvents(events);
      return;
    }

    const query = filters.searchQuery.toLowerCase();
    const filtered = events.filter((event) => {
      const payloadStr = JSON.stringify(event.payload).toLowerCase();
      return (
        event.eventType.toLowerCase().includes(query) ||
        event.contractId.toLowerCase().includes(query) ||
        event.txHash.toLowerCase().includes(query) ||
        payloadStr.includes(query)
      );
    });
    setFilteredEvents(filtered);
  }, [events, filters.searchQuery]);

  const handleFilterChange = useCallback((newFilters: Partial<Filters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
    setCurrentPage(1);
  }, []);

  const handleExport = useCallback(
    (format: "csv" | "json") => {
      const dataToExport = filteredEvents;

      if (!dataToExport.length) {
        showToast("No events available to export.", "warning");
        return;
      }

      try {
        if (format === "json") {
          const blob = new Blob([JSON.stringify(dataToExport, null, 2)], {
            type: "application/json",
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `events-${Date.now()}.json`;
          a.click();
          URL.revokeObjectURL(url);
        } else {
          const headers = ["Contract ID", "Event Type", "Ledger", "Timestamp", "Transaction", "Payload"];
          const rows = dataToExport.map((event) => [
            event.contractId,
            event.eventType,
            event.ledger.toString(),
            event.timestamp,
            event.txHash,
            JSON.stringify(event.payload),
          ]);

          const csv = [
            headers.join(","),
            ...rows.map((row) => row.map((cell) => `"${cell}"`).join(",")),
          ].join("\n");

          const blob = new Blob([csv], { type: "text/csv" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `events-${Date.now()}.csv`;
          a.click();
          URL.revokeObjectURL(url);
        }

        showToast("Event export started.", "success");
      } catch (error) {
        // eslint-disable-next-line no-console
        console.error("Failed to export events:", error);
        showToast("Failed to export events.", "error");
      }
    },
    [filteredEvents, showToast],
  );

  const startIndex = (currentPage - 1) * PAGE_SIZE + 1;
  const endIndex = startIndex + filteredEvents.length - 1;

  return (
    <div className={styles.page}>
      <main className={`${styles.timelineApp} ${styles.explorerApp}`}>
        <header className={styles.hero}>
          <p className={styles.kicker}>SoroScan</p>
          <h1 className={styles.title}>Event Explorer Dashboard</h1>
          <p className={styles.contractId}>
            Browse, filter, and analyze contract events in real-time
          </p>
        </header>

        <FilterBar
          contracts={contracts}
          filters={filters}
          onFilterChange={handleFilterChange}
          onExport={handleExport}
        />

        <section className={styles.timelinePanel} aria-label="Events table">
          <div className={styles.panelHead}>
            <h2 className={styles.sectionTitle}>Contract Events</h2>
            <p className={styles.summary}>
              {loading
                ? "Loading..."
                : `Showing ${startIndex}-${endIndex} of ${totalCount}+`}
            </p>
          </div>

          {error && (
            <div className={`${styles.status} ${styles.error}`} aria-live="polite">
              {error}
            </div>
          )}

          <EventTable
            events={filteredEvents}
            loading={loading}
            onEventClick={setSelectedEvent}
          />

          <PaginationControls
            currentPage={currentPage}
            hasNext={hasNext}
            hasPrev={currentPage > 1}
            onPageChange={setCurrentPage}
            startIndex={startIndex}
            endIndex={endIndex}
            totalCount={totalCount}
          />
        </section>
      </main>

      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}
