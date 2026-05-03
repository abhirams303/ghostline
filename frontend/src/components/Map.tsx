import type { LayerViewModel } from "@/lib/layers";
import type { AnalyzeResponse, Finding, SourceName } from "@/types/findings";

interface MapProps {
  report?: AnalyzeResponse | null;
  visibleLayerIds: string[];
  layers: LayerViewModel[];
}

const sourceAccent: Record<SourceName, string> = {
  strava: "#8ff6d2",
  adsb: "#f2c46b",
  satellite: "#f58b64",
  exa: "#e7ece8",
  system: "#93a2a8"
};

const sourceShadow: Record<SourceName, string> = {
  strava: "0 0 0 10px rgba(143, 246, 210, 0.16)",
  adsb: "0 0 0 10px rgba(242, 196, 107, 0.16)",
  satellite: "0 0 0 10px rgba(245, 139, 100, 0.16)",
  exa: "0 0 0 10px rgba(231, 236, 232, 0.14)",
  system: "0 0 0 10px rgba(147, 162, 168, 0.14)"
};

export function Map({ report, visibleLayerIds, layers }: MapProps) {
  const visibleFindings = (report?.findings ?? []).filter((finding) => isFindingVisible(finding, visibleLayerIds));

  return (
    <section className="overflow-hidden rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] shadow-panel">
      <div className="flex flex-col gap-4 border-b border-white/10 px-5 py-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Map Surface</p>
          <h2 className="mt-2 font-display text-3xl text-[#f2eee4]">
            {report ? report.target.name : "Awaiting target selection"}
          </h2>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Faux tactical view for the scaffold. Layer toggles and evidence positioning still reflect the
            actual backend response.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-2 text-right text-[10px] uppercase tracking-[0.24em] text-white/38">
          <StatChip label="Layers" value={`${layers.length}`} />
          <StatChip label="Visible" value={`${visibleLayerIds.length}`} />
          <StatChip label="Marks" value={`${visibleFindings.length}`} />
        </div>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_280px]">
        <div className="relative min-h-[460px] overflow-hidden rounded-[1.6rem] border border-white/10 bg-[radial-gradient(circle_at_50%_50%,rgba(143,246,210,0.08),transparent_34%),linear-gradient(180deg,#0b0f12_0%,#0d1215_100%)]">
          <div className="absolute inset-0 opacity-50">
            <div className="absolute inset-x-0 top-1/2 h-px bg-white/10" />
            <div className="absolute inset-y-0 left-1/2 w-px bg-white/10" />
            <div className="absolute inset-6 rounded-[1.3rem] border border-white/8" />
            <div className="absolute inset-[16%] rounded-full border border-dashed border-white/10" />
            <div className="absolute inset-[30%] rounded-full border border-dashed border-white/8" />
          </div>

          <div className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 text-center">
            <div className="mx-auto h-5 w-5 rounded-full border-4 border-black/40 bg-[#f2eee4] shadow-[0_0_0_12px_rgba(242,238,228,0.08),0_0_40px_rgba(242,238,228,0.32)]" />
            <div className="mt-3 rounded-full border border-white/12 bg-black/25 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.28em] text-[#f2eee4]">
              {report ? report.target.name : "Target"}
            </div>
          </div>

          {report
            ? report.findings.map((finding, index) => {
                const marker = getFindingMarker(report, finding, index);
                if (!marker || !isFindingVisible(finding, visibleLayerIds)) {
                  return null;
                }

                return (
                  <div
                    key={`${finding.source}-${finding.title}-${index}`}
                    className="absolute z-20 -translate-x-1/2 -translate-y-1/2"
                    style={{ left: `${marker.left}%`, top: `${marker.top}%` }}
                  >
                    <div
                      className="relative h-4 w-4 rounded-full border border-black/30"
                      style={{
                        backgroundColor: sourceAccent[finding.source],
                        boxShadow: sourceShadow[finding.source]
                      }}
                    />
                    <div className="absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 rounded-full border animate-ping opacity-20" />
                  </div>
                );
              })
            : null}

          {!report ? (
            <div className="absolute inset-0 z-20 grid place-items-center p-6">
              <div className="max-w-md rounded-[1.4rem] border border-dashed border-white/10 bg-black/20 p-6 text-center">
                <p className="font-display text-3xl text-[#f2eee4]">Run a target analysis</p>
                <p className="mt-3 text-sm leading-6 text-white/55">
                  The surface will project the target center, active evidence marks, and collector presence
                  once the backend returns a report.
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <div className="space-y-3">
          <div className="rounded-[1.4rem] border border-white/10 bg-black/15 p-4">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#b8c1bd]">Target Fix</p>
            {report ? (
              <div className="mt-4 space-y-3">
                <InfoRow label="Latitude" value={report.target.lat.toFixed(4)} />
                <InfoRow label="Longitude" value={report.target.lon.toFixed(4)} />
                <InfoRow label="Radius" value={`${report.target.radius_km} km`} />
                <InfoRow label="Mode" value={report.mode.toUpperCase()} />
              </div>
            ) : (
              <p className="mt-4 text-sm text-white/55">No target lock yet.</p>
            )}
          </div>

          <div className="rounded-[1.4rem] border border-white/10 bg-black/15 p-4">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#b8c1bd]">Collector Marks</p>
            <div className="mt-4 space-y-2">
              {layers.length > 0 ? (
                layers.map((layer) => (
                  <div
                    key={layer.id}
                    className={`rounded-[1rem] border px-3 py-3 text-sm ${
                      visibleLayerIds.includes(layer.id)
                        ? "border-[#8ff6d2]/30 bg-[#8ff6d2]/8 text-[#eef8f3]"
                        : "border-white/10 bg-black/10 text-white/45"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-[11px] uppercase tracking-[0.24em]">{layer.type}</span>
                      <span className="text-xs">{layer.itemCount}</span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-white/55">No active layers loaded.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function getFindingMarker(report: AnalyzeResponse, finding: Finding, index: number) {
  if (!finding.geo) {
    const fallback = [
      { left: 34, top: 36 },
      { left: 63, top: 32 },
      { left: 68, top: 61 },
      { left: 38, top: 67 }
    ];

    return fallback[index % fallback.length];
  }

  const latDelta = finding.geo.lat - report.target.lat;
  const lonDelta = finding.geo.lon - report.target.lon;
  const scale = Math.max(report.target.radius_km / 12, 0.8);

  return {
    left: clamp(50 + lonDelta * 180 / scale, 12, 88),
    top: clamp(50 - latDelta * 180 / scale, 12, 88)
  };
}

function isFindingVisible(finding: Finding, visibleLayerIds: string[]) {
  if (visibleLayerIds.length === 0) {
    return false;
  }

  return visibleLayerIds.some((layerId) => layerId.toLowerCase().includes(finding.source));
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-white/45">{label}</span>
      <span className="font-mono text-[12px] uppercase tracking-[0.2em] text-[#f2eee4]">{value}</span>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-white/8 bg-black/10 px-3 py-2">
      <div className="text-lg text-[#f2eee4]">{value}</div>
      <div>{label}</div>
    </div>
  );
}
