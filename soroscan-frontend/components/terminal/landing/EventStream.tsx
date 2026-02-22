"use client"

import * as React from "react"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "../Table"

export function EventStream() {
  return (
    <section className="space-y-8">
      <div className="flex items-center gap-4">
        <h2 className="text-2xl font-bold text-terminal-green whitespace-nowrap">
          [LIVE_EVENT_STREAM]
        </h2>
        <div className="h-[2px] w-full bg-terminal-green/20" />
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>TIMESTAMP</TableHead>
            <TableHead>CONTRACT_ID</TableHead>
            <TableHead>EVENT_TYPE</TableHead>
            <TableHead>STATUS</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>2026-02-22T21:42:01</TableCell>
            <TableCell className="text-terminal-cyan">C...9X4Z</TableCell>
            <TableCell>LIQUIDITY_ADD</TableCell>
            <TableCell className="text-terminal-green">PROCESSED</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>2026-02-22T21:41:55</TableCell>
            <TableCell className="text-terminal-cyan">C...2B8Y</TableCell>
            <TableCell>SWAP_COMPLETE</TableCell>
            <TableCell className="text-terminal-green">PROCESSED</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>2026-02-22T21:41:48</TableCell>
            <TableCell className="text-terminal-cyan">C...F7K1</TableCell>
            <TableCell>VAULT_DEPOSIT</TableCell>
            <TableCell className="text-terminal-warning">INGESTING</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>2026-02-22T21:41:30</TableCell>
            <TableCell className="text-terminal-cyan">C...A9S0</TableCell>
            <TableCell>GOV_PROPOSAL</TableCell>
            <TableCell className="text-terminal-green">PROCESSED</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </section>
  )
}
