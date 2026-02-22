"use client"

import * as React from "react"
import { Button } from "../Button"

export function Navbar() {
  return (
    <nav className="border-b border-terminal-green/30 px-8 py-4 flex justify-between items-center bg-terminal-black/50 backdrop-blur-md sticky top-0 z-50">
      <div className="flex items-center gap-2">
        <span className="text-terminal-green text-xl font-bold tracking-tighter">
          [SOROSCAN_PROJECT]
        </span>
      </div>
      <div className="hidden md:flex gap-8 text-xs text-terminal-gray uppercase tracking-widest">
        <a href="#" className="hover:text-terminal-green transition-colors">Explorer</a>
        <a href="#" className="hover:text-terminal-green transition-colors">API_Docs</a>
        <a href="#" className="hover:text-terminal-green transition-colors">GitHub</a>
        <a href="#" className="hover:text-terminal-green transition-colors">Terminal_Access</a>
      </div>
      <Button size="sm" variant="secondary">CONNECT_WALLET</Button>
    </nav>
  )
}
