"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { EventTable } from "./EventTable";
import { FilterBar } from "./FilterBar";
import { EventDetailModal } from "./EventDetailModal";
import { PaginationControls } from "./PaginationControls";
import { AdvancedSearch } from "./AdvancedSearch";
import { BulkActionsToolbar } from "./BulkActionsToolbar";
import { fetchAllContracts, fetchExplorerEvents } from "@/components/ingest/graphql";
import type { EventRecord } from "@/components/ingest/types";
import styles from "@/components/ingest/ingest-terminal.module.css";
import { useToast } from "@/context/ToastContext";
import { parseSearchQuery, matchesFilters } from "@/lib/search-parser";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { useContractEventSubscription } from "@/src/hooks/useContractEventSubscription";
import { SubscriptionStatusBadge } from "@/components/ui/SubscriptionStatusBadge";

const PAGE_SIZE_STORAGE_KEY = "soroscan:page-size";
const DEFAULT_PAGE_SIZE = 25;

interface Filters {
  contractId: string;
  eventType: string;
  since: string;
  until: string;
  searchQuery: string;
  tags: string[];
}

type EventTagMap = Record<string, string[]>;

const EVENT_TAGS_STORAGE_KEY = "soroscan:event-tags";

function normalizeTag(tag: string): string {
  return tag.trim().toLowerCase().replace(/\s+/g, "-");
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
    tags: [],
  });
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [filteredEvents, setFilteredEvents] = useState<EventRecord[]>([]);
  const [eventTags, setEventTags] = useState<EventTagMap>({});
  
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(PAGE_SIZE_STORAGE_KEY);
      return stored ? parseInt(stored, 10) : DEFAULT_PAGE_SIZE;
    }
    return DEFAULT_PAGE_SIZE;
  });

  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [newEventsCount, setNewEventsCount] = useState(0);
  const previousEventsRef = useRef<EventRecord[]>([]);

  // ── Persist page size ──────────────────────────────────────────────────────
  useEffect(() => {
    localStorage.setItem(PAGE_SIZE_STORAGE_KEY, pageSize.toString());
  }, [pageSize]);

  // ── Multi-select state ─────────────────────────────────────────────────────
  /**
   * Memoized selection store keyed by event ID.
   * We intentionally keep this as a Set so membership checks are O(1).
   * The state is reset whenever the page / filters change to avoid stale IDs.
   */
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Reset selection when events change (new page load, filter change, etc.)
  useEffect(() => {
    setSelectedIds(new Set());
  }, [filteredEvents]);

  const handleToggleSelect = useCallback((eventId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  }, []);

  const handleToggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      const allIds = filteredEvents.map((e) => e.id);
      const allSelected = allIds.every((id) => prev.has(id));
      if (allSelected) {
        // Deselect all
        return new Set();
      }
      // Select all visible events
      return new Set(allIds);
    });
  }, [filteredEvents]);

  const handleSelectAll = useCallback(() => {
    setSelectedIds(new Set(filteredEvents.map((e) => e.id)));
  }, [filteredEvents]);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  // Called after successful bulk delete — remove from local state (optimistic UI)
  const handleDeleteSuccess = useCallback(
    (deletedIds: string[]) => {
      const deletedSet = new Set(deletedIds);
      setEvents((prev) => prev.filter((e) => !deletedSet.has(e.id)));
      setSelectedIds(new Set());
      showToast(
        `${deletedIds.length} event${deletedIds.length !== 1 ? "s" : ""} deleted.`,
        "success",
      );
    },
    [showToast],
  );

  // Called after successful bulk tag
  const handleBulkTagSuccess = useCallback(
    (eventIds: string[], tag: string) => {
      setEventTags((prev) => {
        const next = { ...prev };
        for (const id of eventIds) {
          const current = next[id] ?? [];
          if (!current.includes(tag)) {
            next[id] = [...current, tag];
          }
        }
        return next;
      });
      showToast(
        `Tag '${tag}' added to ${eventIds.length} event${eventIds.length !== 1 ? "s" : ""}.`,
        "success",
      );
    },
    [showToast],
  );

  // ── Persist tags ───────────────────────────────────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem(EVENT_TAGS_STORAGE_KEY);
      if (!raw) {
        return;
      }

      const parsed = JSON.parse(raw) as EventTagMap;
      if (parsed && typeof parsed === "object") {
        setEventTags(parsed);
      }
    } catch (error) {
      console.error("Failed to load event tags:", error);
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(EVENT_TAGS_STORAGE_KEY, JSON.stringify(eventTags));
    } catch (error) {
      console.error("Failed to save event tags:", error);
    }
  }, [eventTags]);

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
        const offset = (currentPage - 1) * pageSize;
        const result = await fetchExplorerEvents({
          contractId: filters.contractId,
          eventType: filters.eventType || null,
          limit: pageSize + 1,
          offset,
          since: filters.since || null,
          until: filters.until || null,
        });

        const nextExists = result.length > pageSize;
        const visibleEvents = nextExists ? result.slice(0, pageSize) : result;
        
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
  }, [filters.contractId, filters.eventType, filters.since, filters.until, currentPage, pageSize]);

  // Subscribe to real-time events
  const { events: realTimeEvents, connectionState } = useContractEventSubscription({
    contractId: filters.contractId || "",
    maxEvents: 10,
  });

  // Track new events
  useEffect(() => {
    const previousIds = new Set(previousEventsRef.current.map(e => e.id));
    let count = 0;
    events.forEach(event => {
      if (!previousIds.has(event.id)) {
        count++;
      }
    });

    if (count > 0) {
      if (isPaused) {
        setNewEventsCount(prev => prev + count);
      } else {
        setNewEventsCount(0);
      }
    }

    previousEventsRef.current = events;
  }, [events, isPaused]);

  // Show notification toast for matching events
  useEffect(() => {
    if (realTimeEvents.length > 0 && !isPaused) {
      const newEvent = realTimeEvents[0];
      // Check if new event matches current filters
      const mockEventRecord: EventRecord = {
        id: newEvent.id,
        contractId: filters.contractId || "",
        contractName: "",
        eventType: newEvent.eventType,
        ledger: newEvent.ledgerSequence,
        eventIndex: 0,
        timestamp: newEvent.timestamp,
        txHash: "",
        payload: newEvent.payload,
      };
      
      const parsedQuery = parseSearchQuery(filters.searchQuery);
      if (matchesFilters(mockEventRecord, parsedQuery)) {
        showToast(`New ${newEvent.eventType} event!`, "info", "New Event");
      }

      // Refresh events when new event comes in
      if (currentPage === 1) {
        fetchExplorerEvents({
          contractId: filters.contractId,
          eventType: filters.eventType || null,
          limit: pageSize + 1,
          offset: 0,
          since: filters.since || null,
          until: filters.until || null,
        }).then(result => {
          const nextExists = result.length > pageSize;
          const visibleEvents = nextExists ? result.slice(0, pageSize) : result;
          setEvents(visibleEvents);
          setHasNext(nextExists);
        });
      }
    }
  }, [realTimeEvents, isPaused]);

  // Apply search filter client-side
  useEffect(() => {
    const parsed = parseSearchQuery(filters.searchQuery);
    const filtered = events.filter((event) => {
      if (!matchesFilters(event, parsed)) {
        return false;
      }

      if (!filters.tags.length) {
        return true;
      }

      const tags = eventTags[event.id] ?? [];
      return filters.tags.every((tag) => tags.includes(tag));
    });
    setFilteredEvents(filtered);
  }, [events, filters.searchQuery, filters.tags, eventTags]);

  const handleFilterChange = useCallback((newFilters: Partial<Filters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
    setCurrentPage(1);
  }, []);

  const handleAddTag = useCallback(
    (eventId: string, tagValue: string) => {
      const normalized = normalizeTag(tagValue);
      if (!normalized) {
        return;
      }

      setEventTags((prev) => {
        const current = prev[eventId] ?? [];
        if (current.includes(normalized)) {
          return prev;
        }
        return { ...prev, [eventId]: [...current, normalized] };
      });
      showToast(`Tag '${normalized}' added.`, "success");
    },
    [showToast],
  );

  const handleRemoveTag = useCallback(
    (eventId: string, tagValue: string) => {
      setEventTags((prev) => {
        const current = prev[eventId] ?? [];
        const next = current.filter((tag) => tag !== tagValue);

        if (next.length === current.length) {
          return prev;
        }

        if (!next.length) {
          const { [eventId]: _, ...rest } = prev;
          return rest;
        }

        return { ...prev, [eventId]: next };
      });
    },
    [],
  );

  const tagSuggestions = Array.from(
    new Set([
      ...Object.values(eventTags).flat(),
      ...events.map((event) => normalizeTag(event.eventType)),
      ...events.map((event) => normalizeTag(event.contractName || event.contractId)),
    ]),
  ).sort();

  const handleClearFilters = useCallback(() => {
    setFilters((prev) => ({
      ...prev,
      eventType: "",
      since: "",
      until: "",
      searchQuery: "",
      tags: [],
    }));
    setCurrentPage(1);
  }, []);

  const hasActiveFilters = Boolean(
    filters.eventType || filters.since || filters.until || filters.searchQuery || filters.tags.length
  );
  
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
        console.error("Failed to export events:", error);
        showToast("Failed to export events.", "error");
      }
    },
    [filteredEvents, showToast],
  );

  const handlePageSizeChange = useCallback((newSize: number) => {
    setPageSize(newSize);
    setCurrentPage(1);
  }, []);

  const startIndex = (currentPage - 1) * pageSize + 1;
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
          <div className="absolute top-4 right-4">
            <NotificationBell />
          </div>
        </header>

        <FilterBar
          contracts={contracts}
          filters={filters}
          onFilterChange={handleFilterChange}
          onExport={handleExport}
          tagSuggestions={tagSuggestions}
        />

        <AdvancedSearch 
          onSearch={(q) => handleFilterChange({ searchQuery: q })}
          initialQuery={filters.searchQuery}
        />

        <section className={styles.timelinePanel} aria-label="Events table">
          <div className={styles.panelHead}>
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              <h2 className={styles.sectionTitle}>Contract Events</h2>
              <SubscriptionStatusBadge connectionState={connectionState} />
              {newEventsCount > 0 && (
                <button
                  type="button"
                  className={styles.btn}
                  style={{
                    backgroundColor: "rgba(0, 255, 156, 0.2)",
                    borderColor: "rgba(0, 255, 156, 0.6)",
                  }}
                  onClick={() => setNewEventsCount(0)}
                >
                  {newEventsCount} new event{newEventsCount !== 1 ? "s" : ""}
                </button>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              <p className={styles.summary}>
                {loading
                  ? "Loading..."
                  : `Showing ${startIndex}-${endIndex} of ${totalCount}+`}
              </p>
              <button
                type="button"
                className={styles.btn}
                onClick={() => {
                  setIsPaused(prev => !prev);
                  if (isPaused) {
                    setNewEventsCount(0);
                  }
                }}
              >
                {isPaused ? "▶ Resume" : "⏸ Pause"}
              </button>
            </div>
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
            eventTags={eventTags}
            tagSuggestions={tagSuggestions}
            onAddTag={handleAddTag}
            onRemoveTag={handleRemoveTag}
            showTags
            hasActiveFilters={hasActiveFilters}
            onClearFilters={handleClearFilters}
            selectedIds={selectedIds}
            onToggleSelect={handleToggleSelect}
            onToggleSelectAll={handleToggleSelectAll}
          />

          <PaginationControls
            currentPage={currentPage}
            hasNext={hasNext}
            hasPrev={currentPage > 1}
            onPageChange={setCurrentPage}
            startIndex={startIndex}
            endIndex={endIndex}
            totalCount={totalCount}
            pageSize={pageSize}
            onPageSizeChange={handlePageSizeChange}
          />
        </section>
      </main>

      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}

      {/* Floating bulk actions toolbar – visible when ≥1 events are selected */}
      <BulkActionsToolbar
        selectedIds={selectedIds}
        allEvents={filteredEvents}
        onClearSelection={handleClearSelection}
        onSelectAll={handleSelectAll}
        onDeleteSuccess={handleDeleteSuccess}
        onBulkTagSuccess={handleBulkTagSuccess}
        tagSuggestions={tagSuggestions}
      />
    </div>
  );
}