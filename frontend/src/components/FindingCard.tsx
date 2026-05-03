import type { Finding } from "@/types/findings";

interface FindingCardProps {
  finding: Finding;
}

const severityStyles: Record<Finding["severity"], string> = {
  low: "border-white/10 bg-white/[0.03] text-white/72",
  medium: "border-[#f2c46b]/28 bg-[#f2c46b]/10 text-[#f7ddb0]",
  high: "border-[#f58b64]/35 bg-[#f58b64]/10 text-[#ffd4c6]",
  critical: "border-[#ff875e]/42 bg-[#ff875e]/12 text-[#ffe0d5]"
};

export function FindingCard({ finding }: FindingCardProps) {
  const timestamp = finding.ts ? new Date(finding.ts).toLocaleString() : null;
  const location = finding.geo ? `${finding.geo.lat.toFixed(3)}, ${finding.geo.lon.toFixed(3)}` : null;

  return (
    <article className="rounded-[1.4rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-white/42">{finding.source}</p>
          <h3 className="mt-2 text-lg leading-6 text-[#f2eee4]">{finding.title}</h3>
        </div>
        <span
          className={`rounded-full border px-3 py-2 text-[10px] uppercase tracking-[0.25em] ${severityStyles[finding.severity]}`}
        >
          {finding.severity}
        </span>
      </div>

      <p className="mt-4 text-sm leading-7 text-white/62">{finding.summary}</p>

      <div className="mt-5 grid gap-2 text-[11px] uppercase tracking-[0.22em] text-white/38">
        <MetaRow label="Time" value={timestamp ?? "No timestamp"} />
        <MetaRow label="Geo" value={location ?? "No fix"} />
        <MetaRow label="Signal" value={String(finding.metadata.status ?? "Observed")} />
      </div>

      <div className="mt-5 flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-white/32">
          {Object.keys(finding.metadata).length} metadata fields
        </span>
        {finding.evidence_url ? (
          <a
            href={finding.evidence_url}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-[#8ff6d2]/20 bg-[#8ff6d2]/8 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-[#8ff6d2]"
          >
            source
          </a>
        ) : (
          <span className="rounded-full border border-white/10 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-white/40">
            local stub
          </span>
        )}
      </div>
    </article>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-white/8 pb-2 last:border-b-0 last:pb-0">
      <span>{label}</span>
      <span className="text-right text-white/58">{value}</span>
    </div>
  );
}
