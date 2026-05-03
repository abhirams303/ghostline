import {
  BuildingsIcon,
  GlobeHemisphereWestIcon,
  MapTrifoldIcon,
  MoonIcon,
  MountainsIcon,
} from "@phosphor-icons/react";

import { mapVisualModes, type MapVisualModeId } from "../map/mapConfig";
import { cn } from "../utils/tailwind";
import { Button } from "./primitives/Button";

interface MapModeSwitcherProps {
  activeMode: MapVisualModeId;
  onModeChange(mode: MapVisualModeId): void;
}

const modeIcon = {
  dark: MoonIcon,
  satellite: GlobeHemisphereWestIcon,
  terrain: MountainsIcon,
  urban3d: BuildingsIcon,
};

export function MapModeSwitcher({ activeMode, onModeChange }: MapModeSwitcherProps) {
  return (
    <div className="pointer-events-auto flex max-w-full flex-wrap gap-ui-xxs">
      {mapVisualModes.map((mode) => {
        const Icon = modeIcon[mode.id] ?? MapTrifoldIcon;
        const active = mode.id === activeMode;

        return (
          <Button
            active={active}
            aria-label={mode.description}
            aria-pressed={active}
            className={cn(
              "h-7 min-w-0 rounded-none border bg-background/80 px-ui-xs font-mono text-[10px] uppercase",
              active ? "border-fuel text-fuel" : "border-border text-muted-foreground"
            )}
            key={mode.id}
            onClick={() => onModeChange(mode.id)}
            size="ui"
            type="button"
            variant={active ? "secondary" : "ghost"}
          >
            <Icon size={14} weight={active ? "fill" : "bold"} />
            <span>{mode.shortLabel}</span>
          </Button>
        );
      })}
    </div>
  );
}
