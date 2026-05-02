"use client";

import { useState } from "react";

import { listPresetTargets } from "@/lib/geo";

interface SearchBarProps {
  loading: boolean;
  onSubmit: (query: string, mode: "demo" | "live") => void;
}


export function SearchBar({ loading, onSubmit }: SearchBarProps) {
  const [query, setQuery] = useState("Fort Liberty");
  const [mode, setMode] = useState<"demo" | "live">("live");

  return (
    <div className="rounded-3xl border border-white/10 bg-panel/90 p-4 shadow-panel">
      <div className="flex flex-col gap-3 lg:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Enter a base, route anchor, or unit-associated location"
          className="min-h-14 flex-1 rounded-2xl border border-white/10 bg-black/20 px-4 text-base text-ink outline-none transition focus:border-accent"
        />
        <select
          value={mode}
          onChange={(event) => setMode(event.target.value as "demo" | "live")}
          className="min-h-14 rounded-2xl border border-white/10 bg-black/30 px-4 text-sm uppercase tracking-[0.2em] text-ink"
        >
          <option value="demo">Demo</option>
          <option value="live">Live</option>
        </select>
        <button
          type="button"
          disabled={loading}
          onClick={() => onSubmit(query, mode)}
          className="min-h-14 rounded-2xl bg-accent px-6 text-sm font-semibold uppercase tracking-[0.2em] text-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Analyzing" : "Analyze"}
        </button>
      </div>
      <p className="mt-3 text-xs text-white/55">
        Demo presets: {listPresetTargets().map((target) => target.name).join(", ")}
      </p>
    </div>
  );
}
