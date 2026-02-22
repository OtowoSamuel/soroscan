"use client"

import * as React from "react"
import { Button } from "../Button"

export function Footer() {
  return (
    <>
      {/* CTA Section (Inside Footer for context) */}
      <section className="border-terminal border-terminal-cyan/30 p-12 text-center space-y-8 relative overflow-hidden">
        {/* Decorative bits */}
        <div className="absolute top-4 left-4 text-[10px] text-terminal-cyan/40">SYSTEM_OVERRIDE_ACTIVE</div>
        <div className="absolute bottom-4 right-4 text-[10px] text-terminal-cyan/40">AUTH_MODE: DEV_ADMIN</div>
        
        <h2 className="text-3xl font-bold text-terminal-cyan tracking-tight">
          READY_TO_UPLINK?
        </h2>
        <p className="text-terminal-gray max-w-md mx-auto">
          Join the decentralized indexing network and fuel your Soroban dApps with high-fidelity event data.
        </p>
        <div className="flex justify-center gap-6">
          <Button variant="primary" size="lg">CREATE_API_KEY</Button>
        </div>
      </section>

      <footer className="border-t border-terminal-green/30 p-8 flex flex-col md:flex-row justify-between items-center text-[10px] text-terminal-gray mt-24 gap-4">
        <div className="flex gap-8">
          <span>&copy; 2026 SOROSCAN_INDEXER_SERVICES</span>
          <a href="#" className="hover:text-terminal-green underline underline-offset-4">TERMS_OF_SERVICE</a>
          <a href="#" className="hover:text-terminal-green underline underline-offset-4">PRIVACY_POLICY</a>
        </div>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-terminal-green animate-pulse" />
            STELAR_MAINNET_UPLINK: ONLINE
          </span>
          <span className="border border-terminal-gray/30 px-2 py-0.5">
            LATENCY: 42MS
          </span>
        </div>
      </footer>
    </>
  )
}
