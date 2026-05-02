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
      <section className="rounded-3xl border border-white/10 bg-panel/80 p-5 shadow-panel">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.35em] text-white/50">Threat Brief</p>
          <span className="text-xs text-white/45">streamed narrative</span>
        </div>
        <div className="mt-4 space-y-3">
          <p className="text-sm leading-6 text-white/75">No report yet.</p>
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
    <section className="rounded-3xl border border-white/10 bg-panel/80 p-5 shadow-panel">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.35em] text-white/50">Threat Brief</p>
        <span className="text-xs text-white/45">streamed narrative</span>
      </div>
      <div className="mt-4 space-y-3">
        {streamedChunks.map((chunk, index) => (
          <p key={`${chunk}-${index}`} className="text-sm leading-6 text-white/75">
            {chunk}
          </p>
        ))}
      </div>
    </section>
  );
}
