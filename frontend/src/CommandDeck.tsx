"use client";

import { useEffect, useState } from "react";

import { ActivityStream } from "./components/ActivityStream";
import { AgentRail } from "./components/AgentRail";
import { ConversationBar } from "./components/ConversationBar";
import { IntelPanel } from "./components/IntelPanel";
import { LayerControls } from "./components/LayerControls";
import { TacticalMap } from "./components/TacticalMap";
import { TopBar } from "./components/TopBar";
import { Divider } from "./components/primitives/Divider";
import { useCommandDeck } from "./hooks/useCommandDeck";
import type { MapVisualModeId } from "./map/mapConfig";

export function CommandDeck() {
  const deck = useCommandDeck();
  const [mapMode, setMapMode] = useState<MapVisualModeId>("urban3d");

  useEffect(() => {
    const syncVisualViewportHeight = () => {
      const height = window.visualViewport?.height ?? window.innerHeight;
      document.documentElement.style.setProperty("--command-visual-height", `${height}px`);
    };

    syncVisualViewportHeight();
    window.addEventListener("resize", syncVisualViewportHeight);
    window.visualViewport?.addEventListener("resize", syncVisualViewportHeight);
    return () => {
      window.removeEventListener("resize", syncVisualViewportHeight);
      window.visualViewport?.removeEventListener("resize", syncVisualViewportHeight);
    };
  }, []);

  return (
    <main className="@container/main relative flex h-svh w-full flex-col overflow-hidden bg-black text-foreground">
      <div className="pointer-events-none absolute inset-0 bg-scanlines opacity-35" />
      <TopBar
        busy={deck.busy}
        report={deck.report}
        selectedTargetId={deck.selectedTargetId}
        targets={deck.targets}
        onTargetChange={deck.setActiveMapSurfaceId}
        onRun={() => deck.runAssessment()}
        onSync={deck.syncToAip}
      />

      <section className="relative z-10 flex min-h-0 flex-1">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <section className="relative min-h-0 flex-1 overflow-hidden bg-black">
            <TacticalMap
              activeLayerIds={deck.activeLayerIds}
              activeMapSurfaceId={deck.activeMapSurfaceId}
              mapMode={mapMode}
              onMapModeChange={setMapMode}
              onSurfaceChange={deck.setActiveMapSurfaceId}
              report={deck.report}
              surfaces={deck.surfaces}
              target={deck.selectedTarget}
            />
            <ActivityStream events={deck.events} />
          </section>

          <footer className="command-footer-dock">
            <ConversationBar
              messages={deck.messages}
              onLocationChange={deck.setActiveMapSurfaceId}
              onLocationRequest={deck.focusLocationByName}
              onSend={deck.sendCommand}
              busy={deck.busy}
            />
            <div className="relative hidden h-full overflow-hidden bracket-left bracket-offset-0 bracket-1 bracket-input bg-background @3xl/main:block">
              <LayerControls
                activeLayerIds={deck.activeLayerIds}
                layers={deck.report?.layers ?? []}
                onToggle={deck.toggleLayer}
              />
            </div>
          </footer>
        </section>

        <aside className="hidden w-[440px] shrink-0 flex-col border-l border-background bg-black @5xl/main:flex">
          <AgentRail agents={deck.agents} />
          <div className="relative h-3 mb-separator">
            <div className="absolute -left-[calc(var(--separator)+1px)] right-0 border border-r-0 bg-background p-separator shadow-[0_var(--separator)_0_0_black]">
              <Divider variant="dashed" className="h-1 text-muted dashed-bg-horizontal-tight" />
            </div>
          </div>
          <IntelPanel
            report={deck.report}
            onAnalyze={() => deck.runAssessment()}
            onAskAip={() => deck.askAip("Summarize latest synced assessment for command review.")}
            onReview={deck.reviewTopFinding}
            onSync={deck.syncToAip}
          />
        </aside>
      </section>
    </main>
  );
}
