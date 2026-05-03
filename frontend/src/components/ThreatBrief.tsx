"use client";

import { useEffect, useState } from "react";

import { streamThreatBrief } from "@/lib/api";
import type { AnalyzeResponse } from "@/types/findings";

interface ThreatBriefProps {
  report?: AnalyzeResponse | null;
}

export function ThreatBrief({ report }: ThreatBriefProps) {
  if (!report) {
    return (
      <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
        <div className="flex items-center justify-between">
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Threat Brief</p>
          <span className="text-[11px] uppercase tracking-[0.24em] text-white/38">Idle</span>
        </div>
        <div className="mt-5 rounded-[1.3rem] border border-dashed border-white/10 bg-black/10 p-5 text-sm leading-7 text-white/55">
          No report yet. Once a run completes, the brief streams the narrative replay from the backend’s SSE
          endpoint.
        </div>
      </section>
    );
  }

  return <ThreatBriefBody key={report.run_id} report={report} />;
}

interface ThreatBriefBodyProps {
  report: AnalyzeResponse;
}

function ThreatBriefBody({ report }: ThreatBriefBodyProps) {
  const [streamedChunks, setStreamedChunks] = useState<string[]>([report.narrative_preview]);

  useEffect(() => {
    const stop = streamThreatBrief(report.run_id, (chunk) => {
      setStreamedChunks((current) => {
        if (current[current.length - 1] === chunk) {
          return current;
        }
        return [...current, chunk];
      });
    });

    return stop;
  }, [report.run_id]);

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Threat Brief</p>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Streamed replay of the backend narrative for <span className="text-[#f2eee4]">{report.target.name}</span>.
          </p>
        </div>
        <span className="rounded-full border border-[#8ff6d2]/20 bg-[#8ff6d2]/8 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-[#8ff6d2]">
          streaming
        </span>
      </div>

      <div className="mt-5 space-y-3">
        {streamedChunks.map((chunk, index) => (
          <p
            key={`${chunk}-${index}`}
            className={`rounded-[1.2rem] border px-4 py-3 text-sm leading-7 ${
              index === 0
                ? "border-white/10 bg-black/12 text-[#f2eee4]"
                : "border-white/8 bg-white/[0.03] text-white/72"
            }`}
          >
            {chunk}
          </p>
        ))}
      </div>
    </section>
  );
}
