"use client";

import { useEffect, useMemo, useState } from "react";

import { streamThreatBrief } from "@/lib/api";
import type { AnalyzeResponse } from "@/types/findings";

interface ThreatBriefProps {
  report?: AnalyzeResponse | null;
}

export function ThreatBrief({ report }: ThreatBriefProps) {
  if (!report) {
    return (
      <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5 shadow-panel md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">
            Threat Brief
          </p>
          <span className="text-[11px] uppercase tracking-[0.24em] text-white/38">
            Idle
          </span>
        </div>
        <div className="mt-5 rounded-[1.45rem] border border-dashed border-white/10 bg-black/12 p-6 text-sm leading-7 text-white/55">
          No report yet. Run an analysis and the narrative brief will appear here
          as a single readable summary instead of a stack of status blocks.
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
      ) ?? "Narrative ready",
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

  const paragraphs = useMemo(() => {
    return narrativeBody
      .split(/(?<=[.!?])\s+/)
      .filter(Boolean)
      .reduce<string[]>((chunks, sentence, index) => {
        if (index % 2 === 0) {
          chunks.push(sentence);
          return chunks;
        }

        chunks[chunks.length - 1] = `${chunks[chunks.length - 1]} ${sentence}`;
        return chunks;
      }, []);
  }, [narrativeBody]);

  return (
    <section className="overflow-hidden rounded-[1.9rem] border border-white/10 bg-[linear-gradient(145deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02)),linear-gradient(180deg,rgba(8,12,16,0.92),rgba(10,14,17,0.82))] shadow-panel">
      <div className="grid gap-6 border-b border-white/10 px-5 py-5 md:px-6 md:py-6 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full border border-[#d6d2c4]/18 bg-white/5 px-3 py-2 text-[10px] uppercase tracking-[0.32em] text-[#d6d2c4]">
              Threat Brief
            </span>
            <span className="rounded-full border border-[#8ff6d2]/18 bg-[#8ff6d2]/8 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-[#dff8ec]">
              {statusLine}
            </span>
          </div>

          <h2 className="mt-5 max-w-4xl font-display text-[clamp(2.2rem,4vw,4rem)] leading-[0.94] tracking-[-0.03em] text-[#f2eee4] [text-wrap:balance]">
            Defensive narrative for {report.target.name}
          </h2>
          <p className="mt-4 max-w-3xl text-[15px] leading-7 text-white/60 md:text-base">
            A single synthesized readout of current exposure signals. Collector
            posture stays in the status panel, so this space stays focused on
            what matters.
          </p>
        </div>

        <div className="grid gap-2 sm:grid-cols-3 xl:min-w-[360px]">
          <BriefStat
            label="Mode"
            value={report.mode.toUpperCase()}
            detail={`${report.findings.length} findings`}
          />
          <BriefStat
            label="Generated"
            value={new Date(report.generated_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
            detail={new Date(report.generated_at).toLocaleDateString()}
          />
          <BriefStat
            label="Score"
            value={`${report.score.aggregate}`}
            detail="aggregate exposure"
          />
        </div>
      </div>

      <div className="grid gap-5 px-5 py-5 md:px-6 md:py-6 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0 rounded-[1.55rem] border border-white/10 bg-black/14 p-5 md:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[11px] uppercase tracking-[0.3em] text-[#b8c1bd]">
              Narrative
            </p>
            <span className="text-[11px] uppercase tracking-[0.24em] text-white/35">
              {paragraphs.length} blocks
            </span>
          </div>

          <div className="mt-5 space-y-4">
            {paragraphs.map((paragraph, index) => (
              <p
                key={`${index}-${paragraph}`}
                className="max-w-none text-[15px] leading-8 text-[#f2eee4] md:text-[15.5px] [overflow-wrap:anywhere]"
              >
                {paragraph}
              </p>
            ))}
          </div>
        </div>

        <aside className="grid gap-3 self-start">
          <CalloutCard
            label="Target"
            value={report.target.name}
            detail={`${report.target.lat.toFixed(3)}, ${report.target.lon.toFixed(3)}`}
          />
          <CalloutCard
            label="Coverage"
            value={`${report.layers.length} layers`}
            detail={`${report.source_statuses.filter((status) => status.status === "ok").length} sources healthy`}
          />
          <CalloutCard
            label="Posture"
            value={report.score.aggregate >= 60 ? "Elevated" : "Measured"}
            detail="defensive-use synthesis only"
          />
        </aside>
      </div>
    </section>
  );
}

function BriefStat({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-[1.15rem] border border-white/10 bg-black/14 px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.28em] text-white/40">
        {label}
      </p>
      <p className="mt-2 break-words text-xl text-[#f2eee4] [overflow-wrap:anywhere]">
        {value}
      </p>
      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-white/35">
        {detail}
      </p>
    </div>
  );
}

function CalloutCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-[1.25rem] border border-white/10 bg-white/[0.03] px-4 py-4">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#b8c1bd]">
        {label}
      </p>
      <p className="mt-3 break-words text-base text-[#f2eee4] [overflow-wrap:anywhere]">
        {value}
      </p>
      <p className="mt-2 text-sm leading-6 text-white/50">{detail}</p>
    </div>
  );
}
