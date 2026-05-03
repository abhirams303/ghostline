import type { AnalyzeResponse, SourceStatus } from "@/types/findings";

interface SourceStatusPanelProps {
  report?: AnalyzeResponse | null;
}

const stateStyles: Record<SourceStatus["status"], string> = {
  ok: "border-[#8ff6d2]/25 bg-[#8ff6d2]/8 text-[#def7ec]",
  no_data: "border-white/10 bg-white/[0.03] text-white/72",
  disabled: "border-white/10 bg-white/[0.03] text-white/60",
  missing_config: "border-[#f2c46b]/28 bg-[#f2c46b]/10 text-[#f7ddb0]",
  upstream_error: "border-[#f58b64]/35 bg-[#f58b64]/10 text-[#ffd4c6]"
};

export function SourceStatusPanel({ report }: SourceStatusPanelProps) {
  const statuses = report?.source_statuses ?? [];

  return (
    <section className="rounded-[1.75rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Collector Status</p>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Health and output posture for ADS-B, Exa, and the remaining collection channels.
          </p>
        </div>
        <span className="text-[11px] uppercase tracking-[0.22em] text-white/38">
          {statuses.length} sources
        </span>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {statuses.length > 0 ? (
          statuses.map((status) => <StatusCard key={status.source} status={status} />)
        ) : (
          <div className="rounded-[1.3rem] border border-dashed border-white/10 bg-black/10 p-5 text-sm leading-6 text-white/55 md:col-span-2">
            Run an analysis to see live collector health, including ADS-B source readiness and degraded states.
          </div>
        )}
      </div>
    </section>
  );
}

function StatusCard({ status }: { status: SourceStatus }) {
  return (
    <article className={`rounded-[1.25rem] border p-4 ${stateStyles[status.status]}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em]">{status.source}</p>
          <h3 className="mt-2 text-base text-[#f2eee4]">{formatStatusTitle(status.status)}</h3>
        </div>
        <span className="rounded-full border border-current/20 px-3 py-2 text-[10px] uppercase tracking-[0.24em]">
          {status.status.replace(/_/g, " ")}
        </span>
      </div>

      <p className="mt-4 text-sm leading-6">{status.message}</p>

      <div className="mt-4 grid gap-2 text-[11px] uppercase tracking-[0.22em] text-current/80">
        {Object.entries(status.details).length > 0 ? (
          Object.entries(status.details).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between gap-3 border-b border-current/10 pb-2 last:border-b-0 last:pb-0">
              <span>{formatLabel(key)}</span>
              <span className="text-right">{String(value)}</span>
            </div>
          ))
        ) : (
          <div className="flex items-center justify-between gap-3 border-b border-current/10 pb-2 last:border-b-0 last:pb-0">
            <span>detail</span>
            <span className="text-right">none</span>
          </div>
        )}
      </div>
    </article>
  );
}

function formatStatusTitle(status: SourceStatus["status"]) {
  switch (status) {
    case "ok":
      return "Operational";
    case "no_data":
      return "No current data";
    case "disabled":
      return "Disabled";
    case "missing_config":
      return "Configuration required";
    case "upstream_error":
      return "Upstream degraded";
    default:
      return "Unknown";
  }
}

function formatLabel(value: string) {
  return value.replace(/_/g, " ");
}
