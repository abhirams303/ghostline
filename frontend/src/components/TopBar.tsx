import {
  DatabaseIcon,
  MedalIcon,
  PlayIcon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
  SpinnerIcon,
} from "@phosphor-icons/react";

import type { MissionReport, MissionTarget } from "../domain/types";
import { Button } from "./primitives/Button";

interface TopBarProps {
  busy: boolean;
  report: MissionReport | null;
  selectedTargetId: string;
  targets: MissionTarget[];
  onTargetChange(targetId: string): void;
  onRun(): void;
  onSync(): void;
}

export function TopBar({ busy, report, selectedTargetId, targets, onTargetChange, onRun, onSync }: TopBarProps) {
  const selectedTarget = targets.find((target) => target.id === selectedTargetId) ?? targets[0];

  return (
    <header className="@container/topbar relative z-50 flex min-h-11 flex-row items-center gap-ui-xs border-b border-border bg-subtle-background px-ui-xs py-1 shadow-long">
      <div className="flex min-w-0 flex-1 items-center gap-ui-xs">
        <button
          type="button"
          className="group grid size-9 shrink-0 place-items-center border border-terminal bg-terminal-background font-mono text-xs font-black text-terminal-foreground bracket bracket-terminal bracket-offset-2 bracket-size-6 transition-colors hover:bg-black"
          aria-label="Command operator"
        >
          OC
        </button>
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5 text-xs uppercase">
            <span className="truncate font-bold text-white">OPSEC Command</span>
            <span className="hidden text-subtle-foreground @md/topbar:inline">/</span>
            <button
              type="button"
              className="hidden truncate text-terminal transition-colors hover:text-terminal-foreground @md/topbar:inline"
              onClick={onRun}
            >
              {selectedTarget?.name ?? "---"}
            </button>
          </div>
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10px] uppercase text-muted-foreground">
            <span className="truncate">{report?.runId ?? "standby"}</span>
            <span className="h-1 w-1 shrink-0 bg-accent" />
            <span className="hidden shrink-0 @lg/topbar:inline">AIP {report?.aip.state.replace("_", " ") ?? "not synced"}</span>
          </div>
        </div>
      </div>

      <div className="hidden h-full shrink-0 items-stretch border-x border-border bg-background/50 @6xl/topbar:flex">
        <div className="flex w-28 flex-col justify-center gap-1 px-ui-xs text-xs uppercase">
          <span className="text-[10px] leading-none text-subtle-foreground">Exposure</span>
          <span className="flex items-center gap-1.5 font-semibold text-white tabular-nums">
            <ShieldCheckIcon size={14} weight="bold" className="text-terminal" />
            {report?.score.aggregate ?? "--"}/100
          </span>
        </div>
        <div className="flex w-28 flex-col justify-center gap-1 border-l border-border px-ui-xs text-xs uppercase">
          <span className="text-[10px] leading-none text-subtle-foreground">Findings</span>
          <span className="font-semibold text-white tabular-nums">{report?.findings.length ?? 0} staged</span>
        </div>
      </div>

      <div className="flex shrink-0 items-center justify-end gap-1.5">
        <label className="hidden min-w-36 @2xl/topbar:block">
          <span className="sr-only">Target</span>
          <select
            className="h-8 w-full min-w-0 border border-input bg-background px-2 text-xs font-bold uppercase text-foreground outline-none focus-visible:border-foreground"
            value={selectedTargetId}
            onChange={(event) => onTargetChange(event.target.value)}
          >
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name}
              </option>
            ))}
          </select>
        </label>
        <Button
          className="@max-sm/topbar:size-8 @max-sm/topbar:px-0"
          variant="default"
          size="sm"
          type="button"
          onClick={onRun}
          disabled={busy}
        >
          {busy ? <SpinnerIcon weight="bold" /> : <PlayIcon weight="bold" />}
          <span className="hidden @md/topbar:inline">{busy ? "Running" : "Analyze"}</span>
        </Button>
        <Button
          className="@max-sm/topbar:size-8 @max-sm/topbar:px-0"
          variant="secondary"
          size="sm"
          type="button"
          onClick={onSync}
          disabled={!report || report.aip.state === "syncing"}
        >
          <DatabaseIcon weight="bold" />
          <span className="hidden @md/topbar:inline">Sync</span>
        </Button>
        <Button variant="outline" size="icon-sm" type="button" aria-label="Leaderboard" className="hidden @lg/topbar:inline-flex">
          <MedalIcon weight="bold" />
        </Button>
        <Button variant="outline" size="icon-sm" type="button" aria-label="Settings" className="hidden @lg/topbar:inline-flex">
          <SlidersHorizontalIcon weight="bold" />
        </Button>
      </div>
    </header>
  );
}
