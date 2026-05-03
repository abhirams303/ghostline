import { MapTrifoldIcon } from "@phosphor-icons/react";

import type { MapSurfaceDefinition } from "../map/mapSurfaces";
import { cn } from "../utils/tailwind";
import { Button } from "./primitives/Button";

interface MapSurfaceSwitcherProps {
  activeMapSurfaceId: string;
  onSurfaceChange(surfaceId: string): void;
  surfaces: MapSurfaceDefinition[];
}

export function MapSurfaceSwitcher({
  activeMapSurfaceId,
  onSurfaceChange,
  surfaces,
}: MapSurfaceSwitcherProps) {
  return (
    <div className="pointer-events-auto flex max-w-full flex-wrap gap-ui-xxs">
      {surfaces.map((surface) => {
        const active = surface.id === activeMapSurfaceId;

        return (
          <Button
            active={active}
            aria-pressed={active}
            className={cn(
              "h-7 min-w-0 justify-start rounded-none border bg-background/80 px-ui-xs font-mono text-[10px] uppercase",
              active ? "border-terminal text-terminal" : "border-border text-muted-foreground"
            )}
            key={surface.id}
            onClick={() => onSurfaceChange(surface.id)}
            size="ui"
            type="button"
            variant={active ? "secondary" : "ghost"}
          >
            <MapTrifoldIcon size={14} weight={active ? "fill" : "bold"} />
            <span>{surface.order}</span>
            <span className="hidden max-w-24 truncate @2xl/main:inline">{surface.label}</span>
          </Button>
        );
      })}
    </div>
  );
}
