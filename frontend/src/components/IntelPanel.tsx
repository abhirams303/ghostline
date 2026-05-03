import {
  ChatCircleTextIcon,
  CheckSquareOffsetIcon,
  DatabaseIcon,
  FileTextIcon,
  MagnifyingGlassIcon,
  PlanetIcon,
  ShieldCheckIcon,
} from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { useState } from "react";

import type { Finding, MissionReport } from "../domain/types";
import { PanelTitle } from "./PanelTitle";
import { Badge } from "./primitives/Badge";
import { Button } from "./primitives/Button";
import { Card, CardContent } from "./primitives/Card";
import { Divider } from "./primitives/Divider";
import { ScrollArea } from "./primitives/ScrollArea";

interface IntelPanelProps {
  report: MissionReport | null;
  onAnalyze(): void;
  onAskAip(): void;
  onReview(): void;
  onSync(): void;
}

export function IntelPanel({ report, onAnalyze, onAskAip, onReview, onSync }: IntelPanelProps) {
  const [activeTab, setActiveTab] = useState<"sector" | "findings" | "aip" | "logs">("sector");
  const intelTabs: Array<{ id: "sector" | "findings" | "aip" | "logs"; label: string; icon: ReactNode }> = [
    { id: "sector", label: "Sector", icon: <PlanetIcon weight="bold" /> },
    { id: "findings", label: "Findings", icon: <MagnifyingGlassIcon weight="bold" /> },
    { id: "aip", label: "AIP", icon: <DatabaseIcon weight="bold" /> },
    { id: "logs", label: "Waves", icon: <ChatCircleTextIcon weight="bold" /> },
  ];

  return (
    <Card className="relative min-h-0 flex-1 border-l border-t border-border bg-background/60 dither-mask-md" size="none">
      <CardContent className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto_auto] text-foreground">
        <ScrollArea className="min-h-0">
          <div className="flex flex-col gap-ui-xs p-ui-xs pb-16">
            <header className="flex items-center justify-between gap-ui-xs border-b border-border pb-ui-xs">
              <PanelTitle>{activeTab === "sector" ? "Sector" : activeTab === "logs" ? "Waves" : activeTab}</PanelTitle>
              <FileTextIcon className="text-muted-foreground" weight="bold" />
            </header>
          {report ? (
            <IntelPanelContent activeTab={activeTab} report={report} />
          ) : (
            <section className="grid min-h-72 place-content-center gap-ui-xs text-center">
              <Badge variant="ghost" border="bracket" className="mx-auto">
                No active assessment
              </Badge>
              <p className="m-0 max-w-sm text-sm leading-6 text-muted-foreground">Use the cockpit channel to load live map context or start an AIP-backed assessment.</p>
            </section>
          )}
          </div>
        </ScrollArea>

        <div className="grid grid-cols-4 gap-ui-xs border-t border-border bg-black p-ui-xs">
          <Button variant="secondary" size="sm" type="button" onClick={onAnalyze}>
            <MagnifyingGlassIcon weight="bold" />
          </Button>
          <Button variant="secondary" size="sm" type="button" onClick={onSync} disabled={!report}>
            <DatabaseIcon weight="bold" />
          </Button>
          <Button variant="secondary" size="sm" type="button" onClick={onAskAip} disabled={!report}>
            <FileTextIcon weight="bold" />
          </Button>
          <Button variant="secondary" size="sm" type="button" onClick={onReview} disabled={!report}>
            <CheckSquareOffsetIcon weight="bold" />
          </Button>
        </div>
        <nav className="grid grid-cols-4 gap-panel-gap bg-background px-panel-gap" aria-label="Intelligence panels">
          {intelTabs.map(({ id, label, icon }) => (
            <Button
              active={activeTab === id}
              className="relative flex flex-col items-center justify-center gap-1"
              key={id}
              onClick={() => setActiveTab(id)}
              size="tab"
              type="button"
              variant="tab"
            >
              <span className={activeTab === id ? "absolute inset-0 z-1 cross-lines-terminal-foreground/20" : "hidden"} aria-hidden="true" />
              {icon}
              <span className="truncate text-[10px]">{label}</span>
            </Button>
          ))}
        </nav>
      </CardContent>
    </Card>
  );
}

function IntelPanelContent({
  activeTab,
  report,
}: {
  activeTab: "sector" | "findings" | "aip" | "logs";
  report: MissionReport;
}) {
  if (activeTab === "findings") {
    return (
      <section className="grid gap-separator bg-border">
        {report.findings.map((finding) => (
          <FindingRow finding={finding} key={finding.id} />
        ))}
      </section>
    );
  }

  if (activeTab === "aip") {
    return (
      <section className="grid gap-separator bg-border">
        <section className="grid grid-cols-2 gap-separator bg-border">
          <Readout label="Sync State" value={report.aip.state.replace("_", " ")} />
          <Readout label="Action" value={report.aip.actionName ?? "syncOpsecAnalysisRun"} />
          <Readout label="Object RID" value={report.aip.objectRid ?? "pending"} />
          <Readout label="Operation" value={report.aip.operationId ?? report.runId} />
        </section>
        <section className="grid gap-ui-xs bg-background p-ui-xs">
          <PanelTitle>Backend Path</PanelTitle>
          <p className="m-0 border-l-2 border-terminal pl-ui-xs text-sm leading-6 text-muted-foreground">
            This panel is wired through the Palantir adapter boundary, with live map context available now and Ontology actions, AIP prompts, and writeback receipts ready to bind.
          </p>
          <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-ui-xs border border-border bg-subtle-background/40 p-ui-xs">
            <ShieldCheckIcon className="text-success" weight="bold" />
            <span className="text-sm text-muted-foreground">Human review remains explicit before operational use.</span>
          </div>
        </section>
      </section>
    );
  }

  if (activeTab === "logs") {
    return (
      <section className="grid gap-ui-xs">
        {report.mitigationPriorities.map((priority, index) => (
          <article className="flex items-center gap-1 text-xs" key={priority}>
            <div className="h-px w-4 bg-terminal" />
            <div className="bg-background/45 px-2 py-1 font-extrabold uppercase">
              <span className="bg-white px-1 py-px text-black">STEP {index + 1}</span> {priority}
            </div>
          </article>
        ))}
      </section>
    );
  }

  return (
    <div className="grid gap-separator bg-border">
      <section className="grid grid-cols-3 gap-separator bg-border">
        <Readout label="Target" value={report.target.name} />
        <Readout label="Generated" value={new Date(report.generatedAt).toLocaleTimeString()} />
        <Readout label="AIP State" value={report.aip.state.replace("_", " ")} />
      </section>

      <section className="bg-background p-ui-xs">
        <div className="mb-ui-xs flex items-center justify-between">
          <PanelTitle>Command Brief</PanelTitle>
          <Badge variant={report.score.aggregate >= 75 ? "warning" : "secondary"} size="sm">
            {report.score.aggregate}/100
          </Badge>
        </div>
        <p className="m-0 text-sm leading-6 text-muted-foreground">{report.narrative}</p>
      </section>

      <section className="grid gap-ui-xs bg-background p-ui-xs">
        <PanelTitle>Signal Mix</PanelTitle>
        {Object.entries(report.score).map(([label, value]) => (
          <div className="grid grid-cols-[96px_minmax(0,1fr)_36px] items-center gap-ui-xs text-[10px] uppercase" key={label}>
            <span className="truncate font-bold text-muted-foreground">{label}</span>
            <div className="h-1.5 bg-muted">
              <div className={value >= 75 ? "h-full bg-warning" : "h-full bg-terminal"} style={{ width: `${value}%` }} />
            </div>
            <span className="text-right font-bold text-white">{value}</span>
          </div>
        ))}
      </section>
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 bg-background p-ui-xs">
      <span className="block font-mono text-[10px] uppercase text-muted-foreground">{label}</span>
      <strong className="mt-1 block truncate text-xs uppercase text-foreground">{value}</strong>
    </div>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const badgeVariant =
    finding.severity === "high" || finding.severity === "critical"
      ? "warning"
      : finding.severity === "medium"
        ? "secondary"
        : "success";

  return (
    <article className="grid gap-ui-xs bg-background p-ui-xs elbow elbow-offset-1 elbow-size-6">
      <div className="flex min-w-0 items-start justify-between gap-ui-xs">
        <div className="min-w-0">
          <span className="font-mono text-[10px] uppercase text-muted-foreground">
            {finding.source} / {finding.id}
          </span>
          <strong className="mt-1 block text-sm uppercase text-foreground">{finding.title}</strong>
        </div>
        <Badge variant={badgeVariant} size="sm">
          {finding.severity}
        </Badge>
      </div>
      <p className="m-0 text-sm leading-5 text-muted-foreground">{finding.summary}</p>
      <Divider variant="dashed" className="text-border" />
      <footer className="flex items-center justify-between gap-ui-xs font-mono text-[10px] uppercase text-muted-foreground">
        <span className="truncate">{finding.evidence}</span>
        <span>{finding.status}</span>
      </footer>
    </article>
  );
}
