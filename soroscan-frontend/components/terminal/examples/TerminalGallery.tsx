"use client"

import * as React from "react"
import { Button } from "../Button"
import { Card } from "../Card"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "../Table"
import { Modal } from "../Modal"
import { Input } from "../Input"

export default function TerminalGallery() {
  const [isModalOpen, setIsModalOpen] = React.useState(false);

  return (
    <div className="min-h-screen bg-terminal-black text-terminal-green p-8 font-terminal-mono space-y-12">
      <header className="border-b border-terminal-green/30 pb-4">
        <h1 className="text-3xl font-bold tracking-tighter shadow-glow-green/20">
          SOROSCAN_TERMINAL_V1.0
        </h1>
        <p className="text-terminal-gray mt-2">SYSTEM STATUS: OPERATIONAL</p>
      </header>

      {/* Buttons section */}
      <section className="space-y-4">
        <h2 className="text-xl text-terminal-cyan border-l-4 border-terminal-cyan pl-2">01. BUTTON_VARIANTS</h2>
        <div className="flex flex-wrap gap-4">
          <Button variant="primary">ACCESS_DATABASE</Button>
          <Button variant="secondary">SCAN_MODULES</Button>
          <Button variant="danger">WIPE_CACHE</Button>
        </div>
      </section>

      {/* Cards & Table section */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="space-y-4">
          <h2 className="text-xl text-terminal-cyan border-l-4 border-terminal-cyan pl-2">02. DATA_CONTAINER</h2>
          <Card title="NETWORK_TRAFFIC">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span>INBOUND:</span>
                <span className="text-terminal-cyan">1.2 GB/S</span>
              </div>
              <div className="flex justify-between">
                <span>OUTBOUND:</span>
                <span className="text-terminal-cyan">0.8 GB/S</span>
              </div>
              <div className="w-full bg-terminal-green/10 h-2 mt-4">
                 <div className="bg-terminal-green h-full w-2/3 animate-pulse" />
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <h2 className="text-xl text-terminal-cyan border-l-4 border-terminal-cyan pl-2">03. REGISTRY_TABLE</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>PID</TableHead>
                <TableHead>USER</TableHead>
                <TableHead>CPU</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>1024</TableCell>
                <TableCell>ROOT</TableCell>
                <TableCell>0.5%</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>2048</TableCell>
                <TableCell>USR_01</TableCell>
                <TableCell>15.2%</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </section>

      {/* Input & Modal section */}
      <section className="space-y-4 max-w-md">
        <h2 className="text-xl text-terminal-cyan border-l-4 border-terminal-cyan pl-2">04. USER_INTERACTION</h2>
        <Input label="COMMAND_PROMPT" placeholder="Enter instruction..." />
        <Button 
          variant="secondary" 
          className="w-full"
          onClick={() => setIsModalOpen(true)}
        >
          OPEN_SECURE_CHANNEL
        </Button>
      </section>

      <Modal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        title="SECURE_COMMUNICATION"
      >
        <div className="space-y-4">
          <p>WARNING: This channel is monitored by SOROSCAN_SEC_BOT.</p>
          <p className="text-sm opacity-80">Message: Prepare for uplink to stellar network.</p>
          <Button variant="primary" onClick={() => setIsModalOpen(false)}>CONFIRM_LINK</Button>
        </div>
      </Modal>

      <footer className="pt-12 border-t border-terminal-green/30 text-terminal-gray text-[10px] flex justify-between">
        <span>RUNNING ON VERCEL_EDGE</span>
        <span>2026-02-22T22:15:24+01:00</span>
      </footer>
    </div>
  )
}
