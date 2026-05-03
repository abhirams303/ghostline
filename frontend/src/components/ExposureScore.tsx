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

  const tone =
    aggregate >= 75 ? "Escalated" : aggregate >= 45 ? "Watch" : aggregate > 0 ? "Low Signal" : "Standby";

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Exposure Score</p>
          <p className="mt-2 text-sm leading-6 text-white/58">
            Aggregate visibility estimate based on current collector findings.
          </p>
        </div>
        <span className="rounded-full border border-white/10 bg-black/10 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-white/52">
          {tone}
        </span>
      </div>

      <div className="mt-6 grid gap-5 md:grid-cols-[190px_1fr]">
        <div className="relative mx-auto grid h-[190px] w-[190px] place-items-center rounded-full border border-white/10 bg-[radial-gradient(circle_at_50%_40%,rgba(255,255,255,0.1),rgba(255,255,255,0.02))]">
          <div
            className="absolute inset-3 rounded-full"
            style={{
              background: `conic-gradient(from 220deg, #f58b64 0deg, #f2c46b ${aggregate * 3.6}deg, rgba(255,255,255,0.08) ${aggregate * 3.6}deg, rgba(255,255,255,0.08) 360deg)`
            }}
          />
          <div className="absolute inset-8 rounded-full bg-[#0b0f12]" />
          <div className="relative z-10 text-center">
            <div className="font-display text-6xl leading-none text-[#f2eee4]">{aggregate}</div>
            <div className="mt-3 font-mono text-[11px] uppercase tracking-[0.3em] text-white/45">
              aggregate
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {bars.length > 0 ? (
            bars.map(([label, value]) => (
              <div key={label as string}>
                <div className="mb-2 flex justify-between text-[11px] uppercase tracking-[0.24em] text-white/52">
                  <span>{label}</span>
                  <span>{value}</span>
                </div>
                <div className="h-3 rounded-full bg-white/8">
                  <div
                    className="h-3 rounded-full bg-[linear-gradient(90deg,#f2c46b,#f58b64)]"
                    style={{ width: `${value}%` }}
                  />
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-[1.2rem] border border-dashed border-white/10 bg-black/10 p-5 text-sm leading-6 text-white/55">
              No scored report yet. Run an analysis to populate the exposure breakdown.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
