"use client"

import * as React from "react"
import { Card } from "../Card"

export function Features() {
  return (
    <section className="space-y-8">
      <div className="flex items-center gap-4">
        <h2 className="text-2xl font-bold text-terminal-green whitespace-nowrap">
          [SYSTEM_CAPABILITIES]
        </h2>
        <div className="h-[2px] w-full bg-terminal-green/20" />
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card title="SOROBAN_NATIVE" className="h-full">
          <p className="text-sm leading-relaxed">
            Rust smart contract with admin-controlled indexer whitelist and standardized event emission protocols.
          </p>
        </Card>
        <Card title="DJANGO_BACKEND" className="h-full">
          <p className="text-sm leading-relaxed">
            Production-ready REST API with Django Rest Framework and robust PostgreSQL storage architecture.
          </p>
        </Card>
        <Card title="GRAPHQL_PLAYGROUND" className="h-full">
          <p className="text-sm leading-relaxed">
            Flexible event queries with Strawberry GraphQL. Filter by contract, type, ledger, or time range.
          </p>
        </Card>
        <Card title="WEBHOOK_SUBS" className="h-full">
          <p className="text-sm leading-relaxed">
            Real-time event notifications with HMAC-signed payloads powered by Celery and Redis message brokers.
          </p>
        </Card>
        <Card title="HORIZON_INTEGRATION" className="h-full">
          <p className="text-sm leading-relaxed">
            Seamlessly stream ledger events directly from Stellar&apos;s Horizon API using optimized stellar-sdk workers.
          </p>
        </Card>
        <Card title="DEVELOPER_FIRST" className="h-full">
          <p className="text-sm leading-relaxed">
            Built for engineers who need reliable event data without managing complex indexing infrastructure.
          </p>
        </Card>
      </div>
    </section>
  )
}
