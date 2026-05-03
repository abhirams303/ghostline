"use client";

import { useMemo, useState } from "react";

import { ExposureScore } from "@/components/ExposureScore";
import { FindingCard } from "@/components/FindingCard";
import { LayerToggle } from "@/components/LayerToggle";
import { Map } from "@/components/Map";
import { SearchBar } from "@/components/SearchBar";
import { ThreatBrief } from "@/components/ThreatBrief";
import { analyzeTarget } from "@/lib/api";
import { listPresetTargets, resolveTarget } from "@/lib/geo";
import { toLayerViewModels } from "@/lib/layers";
import type { AnalyzeResponse, Severity } from "@/types/findings";

const severityOrder: Severity[] = ["critical", "high", "medium", "low"];

export default function HomePage() {
  const [report, setReport] = useState<AnalyzeResponse | null>(null);
  const [visibleLayerIds, setVisibleLayerIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState("Fort Liberty");

  const layers = useMemo(() => toLayerViewModels(report?.layers ?? []), [report]);
  const presetTargets = useMemo(() => listPresetTargets(), []);
  const findingCounts = useMemo(() => {
    const initial = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const finding of report?.findings ?? []) {
      initial[finding.severity] += 1;
    }
    return initial;
  }, [report]);

  async function handleAnalyze(query: string, mode: "demo" | "live") {
    setLoading(true);
    setError(null);
    setLastQuery(query);

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
    <main className="relative min-h-screen overflow-hidden">
      <div className="ambient-orb ambient-orb-left" />
      <div className="ambient-orb ambient-orb-right" />
      <div className="grid-overlay" />

      <div className="relative mx-auto flex min-h-screen w-full max-w-[1480px] flex-col gap-6 px-4 py-4 md:px-6 md:py-6 xl:px-8">
        <section className="overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(135deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02)),linear-gradient(180deg,rgba(8,12,16,0.9),rgba(8,12,16,0.78))] shadow-panel">
          <div className="grid gap-8 p-6 lg:grid-cols-[1.2fr_0.8fr] lg:p-8">
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-3 text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">
                <span className="rounded-full border border-[#d6d2c4]/20 bg-white/5 px-3 py-2 text-[#d6d2c4]">
                  OPSEC Mirror
                </span>
                <span className="rounded-full border border-[#78f0c8]/20 bg-[#78f0c8]/8 px-3 py-2 text-[#8ff6d2]">
                  Defensive Analysis Only
                </span>
              </div>

              <div className="max-w-4xl">
                <p className="font-display text-[clamp(3rem,7vw,6.25rem)] leading-[0.92] tracking-[-0.04em] text-[#f2eee4]">
                  Public traces become a field dossier in under a minute.
                </p>
                <p className="mt-5 max-w-2xl text-[15px] leading-7 text-[#b5beb9] md:text-base">
                  This frontend turns the current backend scaffold into a believable operations console:
                  target selection, layer control, threat narrative, scoring, and evidence cards in one
                  surface.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <MetricTile
                  label="Preset Targets"
                  value={`${presetTargets.length}`}
                  detail="Fort Liberty, Norfolk Naval, Creech AFB"
                />
                <MetricTile
                  label="Collector Channels"
                  value="04"
                  detail="Strava, ADS-B, Satellite, Exa"
                />
                <MetricTile
                  label="Current Focus"
                  value={report?.target.name ?? lastQuery}
                  detail={report ? report.mode.toUpperCase() : "READY"}
                />
              </div>
            </div>

            <div className="flex h-full flex-col justify-between rounded-[1.75rem] border border-[#d6d2c4]/12 bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02))] p-5">
              <div>
                <p className="text-[11px] uppercase tracking-[0.32em] text-[#f58b64]">Collector Posture</p>
                <div className="mt-4 space-y-3 text-sm leading-6 text-[#c5cbc7]">
                  <p>
                    Live collection remains interface-first. The console is useful now for walkthroughs,
                    cached demos, scoring, and persistence-backed evidence history.
                  </p>
                  <p>
                    The visual direction is deliberate: editorial briefing room rather than generic SaaS
                    dashboard.
                  </p>
                </div>
              </div>

              <div className="mt-6 border-t border-white/10 pt-5">
                <p className="text-[11px] uppercase tracking-[0.32em] text-[#b8c1bd]">Severity Mix</p>
                <div className="mt-4 grid grid-cols-4 gap-2">
                  {severityOrder.map((severity) => (
                    <div
                      key={severity}
                      className="rounded-2xl border border-white/10 bg-black/15 px-3 py-3 text-center"
                    >
                      <div className="text-lg font-semibold text-[#f2eee4]">{findingCounts[severity]}</div>
                      <div className="mt-1 text-[10px] uppercase tracking-[0.28em] text-white/45">
                        {severity}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <SearchBar loading={loading} onSubmit={handleAnalyze} />

        {error ? (
          <div className="rounded-[1.5rem] border border-[#ff875e]/40 bg-[#ff875e]/12 px-5 py-4 text-sm text-[#ffd5c7]">
            {error}
          </div>
        ) : null}

        <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-4">
            <LayerToggle layers={layers} activeLayerIds={visibleLayerIds} onToggle={toggleLayer} />
            <Map report={report} visibleLayerIds={visibleLayerIds} layers={layers} />
          </div>

          <div className="space-y-4">
            <ExposureScore score={report?.score} />
            <ThreatBrief report={report} />
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <aside className="rounded-[1.75rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
            <div className="flex items-center justify-between">
              <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Run Ledger</p>
              <span className="text-xs text-white/40">
                {report ? new Date(report.generated_at).toLocaleTimeString() : "No run"}
              </span>
            </div>

            <div className="mt-5 space-y-4">
              {report ? (
                <>
                  <LedgerRow label="Run ID" value={report.run_id.slice(0, 8).toUpperCase()} />
                  <LedgerRow
                    label="Coordinates"
                    value={`${report.target.lat.toFixed(3)}, ${report.target.lon.toFixed(3)}`}
                  />
                  <LedgerRow label="Radius" value={`${report.target.radius_km} km`} />
                  <LedgerRow label="Narrative" value={`${report.narrative_preview.length} chars`} />
                  <LedgerRow label="Evidence Rows" value={`${report.findings.length}`} />
                  <LedgerRow label="Map Layers" value={`${report.layers.length}`} />
                </>
              ) : (
                <div className="rounded-[1.25rem] border border-dashed border-white/10 bg-black/10 p-5 text-sm leading-6 text-white/55">
                  Pick one of the presets and run a demo. The backend already persists live runs, so this
                  view is now a proper client for it rather than a blank shell.
                </div>
              )}
            </div>
          </aside>

          <section className="rounded-[1.75rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
            <div className="flex items-center justify-between">
              <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Evidence Cards</p>
              <span className="text-xs text-white/45">{report?.findings.length ?? 0} findings</span>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {(report?.findings ?? []).map((finding) => (
                <FindingCard key={`${finding.source}-${finding.title}`} finding={finding} />
              ))}

              {!report ? (
                <div className="rounded-[1.5rem] border border-dashed border-white/10 bg-black/10 p-6 text-sm leading-6 text-white/50">
                  The evidence tray populates after an analysis run. Each card carries severity, source,
                  location, and supporting metadata from the backend response.
                </div>
              ) : null}
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}

function MetricTile({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-[1.4rem] border border-white/10 bg-black/15 p-4">
      <p className="text-[10px] uppercase tracking-[0.32em] text-white/42">{label}</p>
      <div className="mt-3 text-2xl font-semibold text-[#f2eee4]">{value}</div>
      <p className="mt-2 text-sm leading-6 text-white/55">{detail}</p>
    </div>
  );
}

function LedgerRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/8 pb-3 text-sm last:border-b-0 last:pb-0">
      <span className="text-white/48">{label}</span>
      <span className="font-mono text-right text-[13px] uppercase tracking-[0.18em] text-[#f2eee4]">
        {value}
      </span>
    </div>
  );
}
