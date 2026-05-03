"use client";

import { useEffect, useMemo, useState } from "react";

import { streamThreatBrief } from "@/lib/api";
import type { AnalyzeResponse, SourceStatus } from "@/types/findings";

interface ThreatBriefProps {
  report?: AnalyzeResponse | null;
}

export function ThreatBrief({ report }: ThreatBriefProps) {
  if (!report) {
    return (
      <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
        <div className="flex items-center justify-between">
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">
            Threat Brief
          </p>
          <span className="text-[11px] uppercase tracking-[0.24em] text-white/38">
            Idle
          </span>
        </div>
        <div className="mt-5 rounded-[1.3rem] border border-dashed border-white/10 bg-black/10 p-5 text-sm leading-7 text-white/55">
          No report yet. Once a run completes, the brief streams the narrative
          replay from the backend&apos;s SSE endpoint.
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
  const [streamedChunks, setStreamedChunks] = useState<string[]>([]);

  useEffect(() => {
    const stop = streamThreatBrief(report.run_id, (chunk) => {
      setStreamedChunks((current) => {
        if (current.includes(chunk)) {
          return current;
        }
        return [...current, chunk];
      });
    });

    return stop;
  }, [report.run_id]);

  const statusLine = useMemo(
    () =>
      streamedChunks.find((chunk) =>
        chunk.toLowerCase().startsWith("assessing exposure around"),
      ) ?? "Awaiting replay",
    [streamedChunks],
  );

  const narrativeBody = useMemo(() => {
    const replayed = streamedChunks.filter(
      (chunk) => !chunk.toLowerCase().startsWith("assessing exposure around"),
    );

    return replayed.length > 0
      ? replayed.join(" ")
      : report.narrative_preview;
  }, [report.narrative_preview, streamedChunks]);

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">
            Threat Brief
          </p>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Streamed replay of the backend narrative for{" "}
            <span className="text-[#f2eee4]">{report.target.name}</span>.
          </p>
        </div>
        <span className="w-fit rounded-full border border-[#8ff6d2]/20 bg-[#8ff6d2]/8 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-[#8ff6d2]">
          streaming
        </span>
      </div>

      <div className="mt-5 space-y-3">
        <div className="rounded-[1rem] border border-[#8ff6d2]/18 bg-[#8ff6d2]/6 px-4 py-3 text-[11px] uppercase tracking-[0.24em] text-[#dff8ec]">
          {statusLine}
        </div>
        <div className="rounded-[1.25rem] border border-white/10 bg-black/12 px-4 py-4">
          <p className="text-sm leading-7 text-[#f2eee4] [overflow-wrap:anywhere]">
            {narrativeBody}
          </p>
        </div>
        {streamedChunks.length > 2 ? (
          <div className="rounded-[1.15rem] border border-white/8 bg-white/[0.03] px-4 py-3 text-xs uppercase tracking-[0.22em] text-white/42">
            Replay reduced to one continuous brief to avoid duplicate stacked
            chunks.
          </div>
        ) : null}
      </div>

      <div className="mt-5 rounded-[1.3rem] border border-white/10 bg-black/12 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="text-[11px] uppercase tracking-[0.32em] text-[#b8c1bd]">
            Source Health
          </p>
          <span className="text-[11px] uppercase tracking-[0.22em] text-white/38">
            {report.source_statuses.length} collectors
          </span>
        </div>
        <div className="mt-4 space-y-2">
          {report.source_statuses.map((status) => (
            <SourceHealthRow key={status.source} status={status} />
          ))}
        </div>
      </div>
    </section>
  );
}

function SourceHealthRow({ status }: { status: SourceStatus }) {
  const stateStyles: Record<SourceStatus["status"], string> = {
    ok: "border-[#8ff6d2]/25 bg-[#8ff6d2]/8 text-[#def7ec]",
    no_data: "border-white/10 bg-white/[0.03] text-white/72",
    disabled: "border-white/10 bg-white/[0.03] text-white/60",
    missing_config: "border-[#f2c46b]/28 bg-[#f2c46b]/10 text-[#f7ddb0]",
    upstream_error: "border-[#f58b64]/35 bg-[#f58b64]/10 text-[#ffd4c6]",
  };

  return (
    <div
      className={`rounded-[1rem] border px-3 py-3 ${stateStyles[status.status]}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-[11px] uppercase tracking-[0.26em]">
          {status.source}
        </span>
        <span className="text-[10px] uppercase tracking-[0.22em]">
          {status.status.replace(/_/g, " ")}
        </span>
      </div>
      <p className="mt-2 break-words text-sm leading-6 [overflow-wrap:anywhere]">
        {status.message}
      </p>
    </div>
  );
}
