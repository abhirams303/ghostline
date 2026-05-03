import {
  CircleNotchIcon,
  CpuIcon,
  DatabaseIcon,
  RadioIcon,
  RobotIcon,
  ShieldIcon,
  UserIcon,
} from "@phosphor-icons/react";

import type { AgentDescriptor } from "../domain/types";
import { Badge } from "./primitives/Badge";
import { Button } from "./primitives/Button";
import { Divider } from "./primitives/Divider";

interface AgentRailProps {
  agents: AgentDescriptor[];
}

const icons = {
  aip: DatabaseIcon,
  fusion: CpuIcon,
  voice: RadioIcon,
};

export function AgentRail({ agents }: AgentRailProps) {
  const working = agents.filter((agent) => agent.status === "working").length;
  const complete = agents.filter((agent) => agent.status === "complete").length;

  return (
    <section className="bg-background">
      <div className="border-l border-border bg-subtle-background p-ui-sm">
        <div className="flex items-center gap-ui-sm">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="truncate text-sm font-semibold uppercase text-white">OPSEC Wing</div>
              <div className="text-[10px] uppercase text-subtle-foreground">Mapbox live / AIP adapter</div>
            </div>
            <div className="mt-2 flex min-w-0 items-center gap-ui-xxs">
              <Badge variant="secondary" border="elbow" size="sm" className="bg-white/7 font-semibold">
                <UserIcon weight="duotone" className="size-4" />
                <span className="text-muted-foreground">{agents.length}</span>
              </Badge>
              <Badge variant="secondary" border="elbow" size="sm" className="bg-white/7 font-semibold">
                <ShieldIcon weight="duotone" className="size-4" />
                <span className="text-muted-foreground">{complete}</span>
              </Badge>
              <span className="h-1 w-1 shrink-0 bg-accent" />
              <Badge variant={working ? "warning" : "secondary"} border="bracket" size="sm" className="w-24 font-semibold">
                {working ? (
                  <>
                    <CircleNotchIcon weight="duotone" className="animate-spin" size={16} /> Active
                  </>
                ) : (
                  <span className="text-muted-foreground">Inactive</span>
                )}
              </Badge>
            </div>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-y-px text-[10px] uppercase">
            <dt className="text-muted-foreground">Mode</dt>
            <dd className="text-right font-bold text-white">Live map</dd>
            <dt className="text-muted-foreground">Guard</dt>
            <dd className="text-right font-bold text-terminal">Human</dd>
            <dt className="text-muted-foreground">AIP</dt>
            <dd className="text-right font-bold text-white">Adapter</dd>
          </dl>
        </div>
      </div>

      <div className="border-l border-border">
        <div className="grid grid-cols-3">
          {agents.map((agent) => {
            const Icon = icons[agent.id as keyof typeof icons] ?? RobotIcon;
            const active = agent.status === "working" || agent.status === "listening";
            return (
              <Button
                key={agent.id}
                active={active}
                aria-label={agent.name}
                className="relative flex flex-col items-center justify-center gap-1 border-r last:border-r-0"
                size="tab"
                type="button"
                variant="tab"
              >
                <span
                  className={active ? "absolute inset-0 z-1 cross-lines-terminal-foreground/20" : "hidden"}
                  aria-hidden="true"
                />
                <Icon size={20} weight={active ? "fill" : "regular"} />
                <span className="truncate text-[10px]">{agent.name.replace(" Agent", "").replace(" Worker", "")}</span>
              </Button>
            );
          })}
        </div>

        <div className="relative flex flex-row gap-panel-gap px-0 py-panel-gap">
          <div className="absolute inset-0 bottom-0 z-10 dither-mask-sm dither-mask-invert text-card pointer-events-none" />
          <div className="ml-panel-gap w-2 dashed-bg-vertical-tight dashed-bg-muted" />
          <div className="max-h-40 flex-1 overflow-hidden border border-r-0 bg-subtle-background">
            {agents.map((agent) => {
              const Icon = icons[agent.id as keyof typeof icons] ?? RobotIcon;
              return (
                <article
                  className="relative grid grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-ui-xs px-ui-sm py-2 after:absolute after:bottom-0 after:left-ui-sm after:right-0 after:h-px after:bg-white/20 last:after:hidden"
                  key={agent.id}
                >
                  <div className="grid size-8 place-items-center border border-border bg-background">
                    <Icon
                      className={
                        agent.status === "working"
                          ? "text-warning"
                          : agent.status === "complete"
                            ? "text-success"
                            : agent.status === "listening"
                              ? "text-terminal"
                              : "text-muted-foreground"
                      }
                      weight="bold"
                    />
                  </div>
                  <div className="min-w-0">
                    <strong className="block truncate text-xs uppercase text-foreground">{agent.name}</strong>
                    <span className="block truncate text-[11px] text-muted-foreground">{agent.currentTask}</span>
                  </div>
                  <Badge
                    variant={agent.status === "working" ? "warning" : agent.status === "complete" ? "success" : "ghost"}
                    border="elbow"
                    size="sm"
                  >
                    {agent.status}
                  </Badge>
                </article>
              );
            })}
          </div>
        </div>
        <Divider variant="dashed" className="mx-panel-gap mb-panel-gap h-1 text-muted dashed-bg-horizontal-tight" />
      </div>
    </section>
  );
}
