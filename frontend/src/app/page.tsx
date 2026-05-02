"use client";

import { useMemo, useState } from "react";

import { ExposureScore } from "@/components/ExposureScore";
import { FindingCard } from "@/components/FindingCard";
import { LayerToggle } from "@/components/LayerToggle";
import { Map } from "@/components/Map";
import { SearchBar } from "@/components/SearchBar";
import { ThreatBrief } from "@/components/ThreatBrief";
import { analyzeTarget } from "@/lib/api";
import { resolveTarget } from "@/lib/geo";
import { toLayerViewModels } from "@/lib/layers";
import type { AnalyzeResponse } from "@/types/findings";


export default function HomePage() {
  const [report, setReport] = useState<AnalyzeResponse | null>(null);
  const [visibleLayerIds, setVisibleLayerIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const layers = useMemo(() => toLayerViewModels(report?.layers ?? []), [report]);

  async function handleAnalyze(query: string, mode: "demo" | "live") {
    setLoading(true);
    setError(null);

    try {
      const target = resolveTarget(query);
      const nextReport = await analyzeTarget({
        target,
        mode,
        route: [],
        unit_id: null
      });

      setReport(nextReport);
      setVisibleLayerIds(nextReport.layers.filter((layer) => layer.visible).map((layer) => layer.id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to analyze target.");
    } finally {
      setLoading(false);
    }
  }

  function toggleLayer(layerId: string) {
    setVisibleLayerIds((current) =>
      current.includes(layerId) ? current.filter((id) => id !== layerId) : [...current, layerId]
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-6 md:px-6 lg:px-8">
      <section className="grid gap-5 rounded-[2rem] border border-white/10 bg-black/20 p-6 shadow-panel lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <p className="text-xs uppercase tracking-[0.38em] text-accent">Defensive OSINT Mirror</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-ink md:text-5xl">
            What can they see about you from public traces alone?
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-white/68">
            Feed the system a base, route anchor, or known operating area and it returns an adversary-view
            threat brief built from public-source signals and cached demo evidence.
          </p>
        </div>
        <div className="rounded-3xl border border-danger/25 bg-danger/10 p-5 text-sm leading-6 text-white/75">
          <p className="text-xs uppercase tracking-[0.32em] text-danger">Defensive Use Only</p>
          <p className="mt-3">
            This scaffold is framed for OPSEC assessment, training, and mitigation planning. Live collection
            remains interface-first until source access, legal review, and rate limits are explicit.
          </p>
        </div>
      </section>

      <SearchBar loading={loading} onSubmit={handleAnalyze} />

      {error ? (
        <div className="rounded-2xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-4">
          <LayerToggle layers={layers} activeLayerIds={visibleLayerIds} onToggle={toggleLayer} />
          <Map report={report} visibleLayerIds={visibleLayerIds} layers={layers} />
        </div>
        <div className="space-y-4">
          <ExposureScore score={report?.score} />
          <ThreatBrief report={report} />
        </div>
      </div>

      <section className="rounded-[2rem] border border-white/10 bg-panel/80 p-5 shadow-panel">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.35em] text-white/50">Evidence Cards</p>
          <span className="text-xs text-white/45">{report?.findings.length ?? 0} findings</span>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(report?.findings ?? []).map((finding) => (
            <FindingCard key={`${finding.source}-${finding.title}`} finding={finding} />
          ))}
          {!report ? (
            <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-white/50">
              Run a demo analysis to populate findings.
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}
