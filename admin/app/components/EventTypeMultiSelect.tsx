'use client';

import React, { useState, useMemo } from 'react';

// Event type definitions with categories
const EVENT_TYPE_GROUPS = {
  'Trading': ['SWAP_COMPLETE', 'LIQUIDITY_ADD'],
  'Vault': ['VAULT_DEPOSIT', 'YIELD_CLAIMED'],
  'Staking': ['STAKING_LOCK'],
  'Oracle': ['ORACLE_UPDATE'],
  'Governance': ['GOV_PROPOSAL'],
} as const;

const ALL_EVENT_TYPES = [
  'ALL',
  ...Object.values(EVENT_TYPE_GROUPS).flat(),
] as const;

type EventType = typeof ALL_EVENT_TYPES[number];

interface EventTypeMultiSelectProps {
  selected: EventType[];
  onChange: (selected: EventType[]) => void;
  disabled?: boolean;
}

export function EventTypeMultiSelect({
  selected,
  onChange,
  disabled = false,
}: EventTypeMultiSelectProps) {
  const [search, setSearch] = useState('');

  // Filter events based on search
  const filteredGroups = useMemo(() => {
    const searchLower = search.toLowerCase();
    const result: Record<string, EventType[]> = {};
    
    for (const [group, types] of Object.entries(EVENT_TYPE_GROUPS)) {
      const filtered = types.filter(t => 
        t.toLowerCase().includes(searchLower)
      );
      if (filtered.length > 0) {
        result[group] = filtered;
      }
    }
    
    // Always show ALL if it matches search
    if ('ALL'.toLowerCase().includes(searchLower)) {
      result['Special'] = ['ALL'];
    }
    
    return result;
  }, [search]);

  const handleToggle = (type: EventType) => {
    if (disabled) return;
    
    if (type === 'ALL') {
      if (selected.includes('ALL')) {
        onChange([]);
      } else {
        onChange(['ALL']);
      }
      return;
    }
    
    // Remove ALL if selecting specific type
    let newSelected = selected.filter(t => t !== 'ALL');
    
    if (newSelected.includes(type)) {
      newSelected = newSelected.filter(t => t !== type);
    } else {
      newSelected = [...newSelected, type];
    }
    
    onChange(newSelected);
  };

  const handleSelectAll = () => {
    if (disabled) return;
    onChange([...ALL_EVENT_TYPES]);
  };

  const handleSelectNone = () => {
    if (disabled) return;
    onChange([]);
  };

  const isSelected = (type: EventType) => selected.includes(type);
  const isAllSelected = selected.includes('ALL') || selected.length === ALL_EVENT_TYPES.length - 1;
  const isNoneSelected = selected.length === 0;

  return (
    <div className="flex flex-col gap-3">
      {/* Search input */}
      <div className="relative">
        <input
          type="text"
          placeholder="Search event types..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          disabled={disabled}
          className="w-full px-3 py-2 pl-9 text-sm bg-zinc-900 border border-zinc-700 rounded-md
            text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500
            disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>

      {/* Select all/none buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleSelectAll}
          disabled={disabled}
          className="text-xs px-3 py-1.5 rounded bg-zinc-800 text-zinc-300
            hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Select All
        </button>
        <button
          onClick={handleSelectNone}
          disabled={disabled}
          className="text-xs px-3 py-1.5 rounded bg-zinc-800 text-zinc-300
            hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Select None
        </button>
      </div>

      {/* Event type list grouped */}
      <div className="max-h-64 overflow-y-auto border border-zinc-700 rounded-md bg-zinc-900">
        {Object.entries(filteredGroups).map(([group, types]) => (
          <div key={group} className="border-b border-zinc-800 last:border-b-0">
            <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 bg-zinc-800/50">
              {group}
            </div>
            <div className="p-2">
              {types.map((type) => (
                <label
                  key={type}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer
                    hover:bg-zinc-800/50 ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected(type)}
                    onChange={() => handleToggle(type)}
                    disabled={disabled}
                    className="w-4 h-4 rounded border-zinc-600 bg-zinc-800 text-blue-600
                      focus:ring-blue-500 focus:ring-offset-zinc-900"
                  />
                  <span className="text-sm text-zinc-200">{type.replace(/_/g, ' ')}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
        {Object.keys(filteredGroups).length === 0 && (
          <div className="px-3 py-4 text-sm text-zinc-500 text-center">
            No event types match "{search}"
          </div>
        )}
      </div>

      {/* Selection summary */}
      <div className="text-xs text-zinc-500">
        {selected.length === 0 && 'No event types selected'}
        {selected.includes('ALL') && 'All event types selected'}
        {selected.length > 0 && !selected.includes('ALL') && 
          `${selected.length} event type${selected.length > 1 ? 's' : ''} selected`}
      </div>
    </div>
  );
}

export type { EventType };