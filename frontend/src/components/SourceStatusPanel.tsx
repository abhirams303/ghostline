import type { AnalyzeResponse, SourceStatus } from "@/types/findings";

interface SourceStatusPanelProps {
  report?: AnalyzeResponse | null;
}

const stateStyles: Record<SourceStatus["status"], string> = {
  ok: "border-[#8ff6d2]/25 bg-[#8ff6d2]/8 text-[#def7ec]",
  no_data: "border-white/10 bg-white/[0.03] text-white/72",
  disabled: "border-white/10 bg-white/[0.03] text-white/60",
  missing_config: "border-[#f2c46b]/28 bg-[#f2c46b]/10 text-[#f7ddb0]",
  upstream_error: "border-[#f58b64]/35 bg-[#f58b64]/10 text-[#ffd4c6]",
};

export function SourceStatusPanel({ report }: SourceStatusPanelProps) {
  const statuses = report?.source_statuses ?? [];

  return (
    <section className="rounded-[1.75rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">
            Collector Status
          </p>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Compact source posture only. Query internals and extra Exa metadata
            stay out of the main screen.
          </p>
        </div>
        <span className="text-[11px] uppercase tracking-[0.22em] text-white/38">
          {statuses.length} sources
        </span>
      </div>

      <div className="mt-5 grid gap-3">
        {statuses.length > 0 ? (
          statuses.map((status) => (
            <StatusCard key={status.source} status={status} />
          ))
        ) : (
          <div className="rounded-[1.3rem] border border-dashed border-white/10 bg-black/10 p-5 text-sm leading-6 text-white/55">
            Run an analysis to see live collector health.
          </div>
        )}
      </div>
    </section>
  );
}

function StatusCard({ status }: { status: SourceStatus }) {
  const detailItems = getCompactDetails(status);

  return (
    <article className={`min-w-0 rounded-[1.25rem] border p-4 ${stateStyles[status.status]}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] uppercase tracking-[0.28em]">
              {status.source}
            </p>
            <span className="rounded-full border border-current/20 px-2 py-1 text-[9px] uppercase tracking-[0.22em]">
              {status.status.replace(/_/g, " ")}
            </span>
          </div>
          <p className="mt-3 break-words text-sm leading-6 [overflow-wrap:anywhere]">
            {status.message}
          </p>
        </div>
      </div>

      {detailItems.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {detailItems.map(({ label, value }) => (
            <span
              key={`${label}-${value}`}
              className="rounded-full border border-current/15 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-current/82"
            >
              {label}: {value}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function getCompactDetails(status: SourceStatus) {
  const details = status.details ?? {};

  if (status.source === "exa") {
    return [
      chip("findings", details.finding_count),
      chip("queries", details.executed_queries ?? details.query_family_count),
      chip("failures", details.failed_queries),
    ].filter(Boolean) as Array<{ label: string; value: string }>;
  }

  if (status.source === "adsb") {
    return [
      chip("findings", details.finding_count),
      chip("samples", details.sample_count ?? details.snapshot_count),
      chip("tracks", details.aircraft_count ?? details.raw_aircraft_rows),
    ].filter(Boolean) as Array<{ label: string; value: string }>;
  }

  if (status.source === "strava") {
    return [
      chip("findings", details.finding_count),
      chip("tiles", details.tile_count),
      chip("zoom", details.zoom),
    ].filter(Boolean) as Array<{ label: string; value: string }>;
  }

  if (status.source === "satellite") {
    return [chip("next pass", details.next_pass)].filter(Boolean) as Array<{
      label: string;
      value: string;
    }>;
  }

  return [];
}

function chip(label: string, value: unknown) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const text =
    typeof value === "string" ? value.replace(/_/g, " ") : String(value);

  return {
    label,
    value: text,
  };
}
