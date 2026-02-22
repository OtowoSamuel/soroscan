"use client"

import * as React from "react"
import { Button } from "../Button"

export function Hero() {
  return (
    <section className="flex flex-col items-center text-center space-y-8 py-12">
      <div className="relative">
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-terminal-green animate-pulse">
          SOROSCAN
        </h1>
        <div className="absolute -top-4 -right-8 text-xs bg-terminal-cyan text-terminal-black px-1 font-bold">
          v1.0.42_STABLE
        </div>
      </div>
      <div className="max-w-2xl space-y-4">
        <p className="text-xl md:text-2xl text-terminal-cyan border-y border-terminal-cyan/20 py-4">
          &gt; THE_GRAPH_FOR_SOROBAN
        </p>
        <p className="text-terminal-gray max-w-lg mx-auto">
          Index, query, and subscribe to smart contract events on the Stellar blockchain. 
          Reliable event ingestion for high-availability decentralized applications.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row gap-4 pt-4">
        <Button size="lg" variant="primary">START_INDEXING</Button>
        <Button size="lg" variant="secondary">VIEW_DOCUMENTATION</Button>
      </div>
    </section>
  )
}
