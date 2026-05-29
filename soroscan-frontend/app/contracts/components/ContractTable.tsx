"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/terminal/Table";
import { Button } from "@/components/terminal/Button";
import type { Contract } from "@/components/ingest/contract-types";
import { ContractEmptyState } from "./ContractEmptyState";

interface ContractTableProps {
  contracts: Contract[];
  onDelete: (id: string) => void;
  onRegister: () => void;
}

export function ContractTable({ contracts, onDelete, onRegister }: ContractTableProps) {
  const router = useRouter();

  const handleRowClick = (id: string) => {
    router.push(`/contracts/${id}`);
  };

  if (contracts.length === 0) {
    return <ContractEmptyState onRegister={onRegister} />;
  }

  return (
    <>
      {/* ── Mobile card view (< 640px) ── */}
      <div className="flex flex-col gap-3 sm:hidden">
        {contracts.map((contract) => (
          <div
            key={contract.id}
            onClick={() => handleRowClick(contract.id)}
            className="cursor-pointer border border-terminal-green/20 bg-terminal-green/5 p-4 flex flex-col gap-3"
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="text-xs text-terminal-cyan uppercase mb-1">Contract ID</div>
                <div className="font-mono text-terminal-cyan text-sm">
                  {contract.contractId.slice(0, 8)}...
                </div>
              </div>
              <span
                className={`inline-flex items-center gap-2 px-2 py-1 text-xs font-mono ${
                  contract.status === "active"
                    ? "text-terminal-green border border-terminal-green/30 bg-terminal-green/10"
                    : "text-terminal-gray border border-terminal-gray/30 bg-terminal-gray/10"
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    contract.status === "active"
                      ? "bg-terminal-green animate-pulse"
                      : "bg-terminal-gray"
                  }`}
                />
                {contract.status.toUpperCase()}
              </span>
            </div>

            <div>
              <div className="text-xs text-terminal-cyan uppercase mb-1">Name</div>
              <div className="font-semibold text-sm">{contract.name}</div>
            </div>

            <div className="flex justify-between items-center">
              <div>
                <div className="text-xs text-terminal-cyan uppercase mb-1">Events</div>
                <div className="font-mono text-sm">{contract.eventCount.toLocaleString()}</div>
              </div>
              <Button
                variant="danger"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(contract.id);
                }}
              >
                Delete
              </Button>
            </div>

            {contract.tags && contract.tags.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {contract.tags.slice(0, 3).map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-2 py-0.5 bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/30"
                  >
                    {tag}
                  </span>
                ))}
                {(contract.tags?.length ?? 0) > 3 && (
                  <span className="text-xs text-terminal-gray">
                    +{(contract.tags?.length ?? 0) - 3}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Desktop table view (≥ 640px) ── */}
      <div className="hidden sm:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Contract ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Events</TableHead>
              <TableHead>Tags</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {contracts.map((contract) => (
              <TableRow
                key={contract.id}
                onClick={() => handleRowClick(contract.id)}
                className="cursor-pointer"
              >
                <TableCell className="font-mono text-terminal-cyan">
                  {contract.contractId.slice(0, 8)}...
                </TableCell>
                <TableCell className="font-semibold">{contract.name}</TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center gap-2 px-2 py-1 text-xs font-mono ${
                      contract.status === "active"
                        ? "text-terminal-green border border-terminal-green/30 bg-terminal-green/10"
                        : "text-terminal-gray border border-terminal-gray/30 bg-terminal-gray/10"
                    }`}
                  >
                    <span
                      className={`w-2 h-2 rounded-full ${
                        contract.status === "active"
                          ? "bg-terminal-green animate-pulse"
                          : "bg-terminal-gray"
                      }`}
                    />
                    {contract.status.toUpperCase()}
                  </span>
                </TableCell>
                <TableCell className="font-mono">{contract.eventCount.toLocaleString()}</TableCell>
                <TableCell>
                  <div className="flex gap-1 flex-wrap">
                    {contract.tags?.slice(0, 3).map((tag) => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-0.5 bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/30"
                      >
                        {tag}
                      </span>
                    ))}
                    {(contract.tags?.length ?? 0) > 3 && (
                      <span className="text-xs text-terminal-gray">
                        +{(contract.tags?.length ?? 0) - 3}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(contract.id);
                    }}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}