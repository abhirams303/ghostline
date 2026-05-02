import type { Finding } from "@/types/findings";

interface FindingCardProps {
  finding: Finding;
}


const SEVERITY_STYLES: Record<Finding["severity"], string> = {
  low: "border-white/10 text-white/70",
  medium: "border-warning/40 text-warning",
  high: "border-danger/60 text-danger",
  critical: "border-danger text-danger"
};


export function FindingCard({ finding }: FindingCardProps) {
  return (
    <article className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold">{finding.title}</p>
        <span className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-[0.25em] ${SEVERITY_STYLES[finding.severity]}`}>
          {finding.severity}
        </span>
      </div>
      <p className="mt-3 text-sm text-white/65">{finding.summary}</p>
      <div className="mt-4 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-white/45">
        <span>{finding.source}</span>
        {finding.evidence_url ? (
          <a href={finding.evidence_url} target="_blank" rel="noreferrer" className="text-accent">
            source
          </a>
        ) : (
          <span>stub</span>
        )}
      </div>
    </article>
  );
}
