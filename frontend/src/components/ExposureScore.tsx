import type { ScoreBreakdown } from "@/types/findings";

interface ExposureScoreProps {
  score?: ScoreBreakdown;
}


export function ExposureScore({ score }: ExposureScoreProps) {
  const aggregate = score?.aggregate ?? 0;
  const bars = score
    ? [
        ["Movement", score.movement],
        ["Personnel", score.personnel],
        ["Facility", score.facility],
        ["Aerial", score.aerial]
      ]
    : [];

  return (
    <section className="rounded-3xl border border-white/10 bg-panel/80 p-5 shadow-panel">
      <p className="text-xs uppercase tracking-[0.35em] text-white/50">Exposure Score</p>
      <div className="mt-4 flex items-end justify-between gap-4">
        <div>
          <div className="text-6xl font-semibold text-accent">{aggregate}</div>
          <div className="text-sm text-white/60">Aggregate adversary visibility estimate</div>
        </div>
      </div>
      <div className="mt-6 space-y-3">
        {bars.map(([label, value]) => (
          <div key={label as string}>
            <div className="mb-1 flex justify-between text-xs text-white/60">
              <span>{label}</span>
              <span>{value}</span>
            </div>
            <div className="h-2 rounded-full bg-white/10">
              <div
                className="h-2 rounded-full bg-gradient-to-r from-warning to-danger"
                style={{ width: `${value}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
