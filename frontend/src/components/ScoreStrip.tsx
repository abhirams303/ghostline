import type { MissionReport } from "../domain/types";
import { cn } from "../utils/tailwind";
import { Badge } from "./primitives/Badge";

interface ScoreStripProps {
  className?: string;
  report: MissionReport | null;
}

export function ScoreStrip({ className, report }: ScoreStripProps) {
  const score = report?.score;
  const metrics = [
    ["Aggregate", score?.aggregate ?? 0],
    ["Movement", score?.movement ?? 0],
    ["Personnel", score?.personnel ?? 0],
    ["Facility", score?.facility ?? 0],
    ["Aerial", score?.aerial ?? 0],
  ] as const;

  return (
    <section className={cn("@container/score grid grid-cols-2 gap-separator bg-border @3xl/score:grid-cols-5", className)}>
      {metrics.map(([label, value], index) => (
        <article
          className={[
            "relative min-h-[72px] min-w-0 overflow-hidden bg-background px-ui-xs py-ui-xs bracket bracket-subtle bracket-offset-0 bracket-size-6 @3xl/score:min-h-24",
            index === 0 ? "col-span-2 @3xl/score:col-span-1" : "",
          ].join(" ")}
          key={label}
        >
          <div className="flex items-center justify-between gap-ui-xs">
            <span className="truncate font-mono text-[10px] uppercase text-muted-foreground">{label}</span>
            {index === 0 ? (
              <Badge variant={value >= 75 ? "warning" : "secondary"} size="sm">
                {report ? report.mode : "standby"}
              </Badge>
            ) : null}
          </div>
          <div className="mt-ui-xxs flex items-end justify-between gap-ui-xs @3xl/score:mt-ui-xs">
            <div className="font-mono text-2xl font-black text-foreground @3xl/score:text-3xl">{value}</div>
            <span className="hidden font-mono text-[10px] uppercase text-muted-foreground @lg/score:block">
              {value >= 75 ? "watch" : value >= 55 ? "review" : "clear"}
            </span>
          </div>
          <div className="mt-ui-xxs h-1.5 overflow-hidden bg-muted @3xl/score:mt-ui-xs">
            <div
              className={
                value >= 75
                  ? "h-full bg-destructive"
                  : value >= 55
                    ? "h-full bg-warning"
                    : "h-full bg-success"
              }
              style={{ width: `${value}%` }}
            />
          </div>
        </article>
      ))}
    </section>
  );
}
