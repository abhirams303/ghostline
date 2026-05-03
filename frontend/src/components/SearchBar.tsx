"use client";

import { useState } from "react";

import { listPresetTargets } from "@/lib/geo";

interface SearchBarProps {
  loading: boolean;
  onSubmit: (query: string, mode: "demo" | "live") => void;
}

export function SearchBar({ loading, onSubmit }: SearchBarProps) {
  const presets = listPresetTargets();
  const [query, setQuery] = useState("Fort Liberty");
  const [mode, setMode] = useState<"demo" | "live">("live");

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-4 shadow-panel md:p-5">
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Target Command</p>
            <p className="mt-2 text-sm leading-6 text-white/58">
              Choose a preset target or type a known operating area. Unknown input currently resolves to the
              closest demo-safe preset.
            </p>
          </div>
          <span className="hidden rounded-full border border-[#8ff6d2]/20 bg-[#8ff6d2]/8 px-3 py-2 text-[10px] uppercase tracking-[0.3em] text-[#8ff6d2] md:inline-flex">
            Backend Connected
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => setQuery(preset.name)}
              className={`rounded-full border px-3 py-2 text-[11px] uppercase tracking-[0.24em] transition ${
                query === preset.name
                  ? "border-[#f2eee4]/30 bg-white/10 text-[#f2eee4]"
                  : "border-white/10 bg-black/10 text-white/52 hover:text-white/78"
              }`}
            >
              {preset.name}
            </button>
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_auto_auto]">
          <label className="group flex min-h-16 items-center gap-3 rounded-[1.4rem] border border-white/10 bg-black/20 px-4 transition focus-within:border-[#8ff6d2]/40">
            <span className="font-mono text-xs uppercase tracking-[0.28em] text-white/35">Query</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Fort Liberty"
              className="w-full bg-transparent text-base text-[#f2eee4] outline-none placeholder:text-white/28"
            />
          </label>

          <div className="grid grid-cols-2 rounded-[1.4rem] border border-white/10 bg-black/20 p-1">
            {(["live", "demo"] as const).map((nextMode) => {
              const active = mode === nextMode;
              return (
                <button
                  key={nextMode}
                  type="button"
                  onClick={() => setMode(nextMode)}
                  className={`rounded-[1rem] px-4 py-3 text-[11px] uppercase tracking-[0.28em] transition ${
                    active
                      ? "bg-[#f2eee4] text-black"
                      : "text-white/55 hover:bg-white/5 hover:text-white/82"
                  }`}
                >
                  {nextMode}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            disabled={loading}
            onClick={() => onSubmit(query, mode)}
            className="min-h-16 rounded-[1.4rem] border border-[#8ff6d2]/35 bg-[linear-gradient(135deg,#8ff6d2,#d9f3b1)] px-6 text-sm font-semibold uppercase tracking-[0.28em] text-black transition hover:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-55"
          >
            {loading ? "Running" : "Analyze"}
          </button>
        </div>
      </div>
    </section>
  );
}
