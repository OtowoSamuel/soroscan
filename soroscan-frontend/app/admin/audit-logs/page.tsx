"use client";

import * as React from "react";
import {
  Search,
  Shield,
  User,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { ResponsiveTable } from "@/components/terminal/ResponsiveTable";
import { Button } from "@/components/terminal/Button";
import { Input } from "@/components/terminal/Input";

interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  timestamp: string;
  details: string;
}

const COLUMNS = [
  { key: "timestamp", label: "Timestamp", sortable: true },
  { key: "actor", label: "Actor", sortable: true },
  { key: "action", label: "Action", sortable: true },
  { key: "target", label: "Target", sortable: true },
  { key: "details", label: "Details" },
];

const SAMPLE_DATA: AuditLogEntry[] = [
  {
    id: "log_001",
    actor: "0x1a2b3c...",
    action: "VERIFY_APPROVE",
    target: "CCAAA",
    timestamp: "2025-01-15T10:30:00Z",
    details: "Contract verification approved",
  },
  {
    id: "log_002",
    actor: "0x4d5e6f...",
    action: "VERIFY_REJECT",
    target: "CCBBB",
    timestamp: "2025-01-15T09:15:00Z",
    details: "Contract verification rejected - missing ABI",
  },
  {
    id: "log_003",
    actor: "admin",
    action: "ROLE_CHANGE",
    target: "0x7g8h9i...",
    timestamp: "2025-01-14T14:00:00Z",
    details: "Changed role from viewer to editor",
  },
];

export default function AuditLogsPage() {
  const [logs] = React.useState<AuditLogEntry[]>(SAMPLE_DATA);
  const [search, setSearch] = React.useState("");
  const [actionFilter, setActionFilter] = React.useState("all");
  const [currentPage, setCurrentPage] = React.useState(1);
  const pageSize = 10;

  const filtered = React.useMemo(() => {
    return logs.filter((log) => {
      const matchesSearch =
        search === "" ||
        log.actor.toLowerCase().includes(search.toLowerCase()) ||
        log.action.toLowerCase().includes(search.toLowerCase()) ||
        log.target.toLowerCase().includes(search.toLowerCase());
      const matchesAction =
        actionFilter === "all" || log.action === actionFilter;
      return matchesSearch && matchesAction;
    });
  }, [logs, search, actionFilter]);

  const totalPages = Math.ceil(filtered.length / pageSize);
  const paginated = filtered.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  React.useEffect(() => {
    setCurrentPage(1);
  }, [search, actionFilter]);

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 space-y-6" data-testid="audit-logs-page">
      <div>
        <h1 className="text-base font-mono font-semibold text-green-400">
          Audit Logs
        </h1>
        <p className="text-xs font-mono text-gray-500 mt-0.5">
          User activity, contract verification, and role changes
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex-1 min-w-[240px] max-w-md">
          <Input
            placeholder="Search actor, action, target..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="audit-search"
          />
        </div>
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="bg-terminal-black border border-terminal-green/50 px-3 py-2 text-sm font-terminal-mono text-terminal-green focus-visible:outline-none focus-visible:border-terminal-green"
          data-testid="action-filter"
        >
          <option value="all">All Actions</option>
          <option value="VERIFY_APPROVE">Verify Approve</option>
          <option value="VERIFY_REJECT">Verify Reject</option>
          <option value="ROLE_CHANGE">Role Change</option>
        </select>
      </div>

      <div className="border border-terminal-green/30 overflow-auto">
        <table className="w-full caption-bottom text-sm font-terminal-mono">
          <thead>
            <tr className="bg-terminal-green/10 border-b border-terminal-green">
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className="h-10 px-4 text-left align-middle font-bold text-terminal-cyan uppercase tracking-wider"
                >
                  <div className="flex items-center gap-2">
                    {col.label}
                    {col.sortable && <ArrowUpDown size={10} />}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginated.length === 0 ? (
              <tr>
                <td
                  colSpan={COLUMNS.length}
                  className="p-8 text-center text-terminal-gray"
                >
                  No audit logs found
                </td>
              </tr>
            ) : (
              paginated.map((log) => (
                <tr
                  key={log.id}
                  className="border-b border-terminal-green/30 hover:bg-terminal-green/10 transition-colors"
                >
                  <td className="px-4 py-3 text-terminal-gray whitespace-nowrap">
                    {log.timestamp}
                  </td>
                  <td className="px-4 py-3 text-terminal-green">
                    <span className="flex items-center gap-2">
                      <User size={14} />
                      {log.actor}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono ${
                        log.action === "VERIFY_APPROVE"
                          ? "bg-green-900/40 text-green-400"
                          : log.action === "VERIFY_REJECT"
                          ? "bg-red-900/40 text-red-400"
                          : log.action === "ROLE_CHANGE"
                          ? "bg-blue-900/40 text-blue-400"
                          : "bg-terminal-green/10 text-terminal-green"
                      }`}
                    >
                      <Shield size={12} />
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-terminal-green font-mono">
                    {log.target}
                  </td>
                  <td className="px-4 py-3 text-terminal-gray text-xs">
                    {log.details}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs font-terminal-mono text-terminal-gray">
            Showing {(currentPage - 1) * pageSize + 1}–
            {Math.min(currentPage * pageSize, filtered.length)} of{" "}
            {filtered.length} entries
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              data-testid="prev-page"
            >
              <ChevronLeft size={14} /> Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              data-testid="next-page"
            >
              Next <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
