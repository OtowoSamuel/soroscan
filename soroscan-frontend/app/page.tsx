"use client"

import * as React from "react"
import { Navbar } from "@/components/terminal/landing/Navbar"
import { Hero } from "@/components/terminal/landing/Hero"
import { Features } from "@/components/terminal/landing/Features"
import { EventStream } from "@/components/terminal/landing/EventStream"
import { Footer } from "@/components/terminal/landing/Footer"

export default function Home() {
  return (
    <div className="min-h-screen font-terminal-mono selection:bg-terminal-green selection:text-terminal-black">
      <Navbar />

      <main className="container mx-auto px-8 py-16 space-y-24">
        <Hero />
        <Features />
        <EventStream />
        <Footer />
      </main>

      {/* Global Background Deco */}
      <div className="fixed inset-0 pointer-events-none z-[-1] overflow-hidden opacity-20">
         <div className="absolute top-0 left-0 w-full h-1 bg-terminal-green shadow-glow-green animate-[scan_8s_linear_infinite]" />
         <div className="absolute inset-0 bg-[linear-gradient(rgba(0,255,65,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,65,0.03)_1px,transparent_1px)] bg-[size:40px_40px]" />
      </div>
    </div>
  )
}
