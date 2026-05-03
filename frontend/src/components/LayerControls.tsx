import type { MapLayer } from "../domain/types";
import { cn } from "../utils/tailwind";
import { Button } from "./primitives/Button";
import { Divider } from "./primitives/Divider";

interface LayerControlsProps {
  className?: string;
  activeLayerIds: string[];
  layers: MapLayer[];
  onToggle(layerId: string): void;
}

const dotClass = {
  amber: "bg-warning",
  blue: "bg-fuel",
  green: "bg-success",
  red: "bg-destructive",
};

export function LayerControls({ className, activeLayerIds, layers, onToggle }: LayerControlsProps) {
  if (layers.length === 0) {
    return (
      <section className={cn("grid h-full place-items-center bg-background px-ui-xs py-ui-xs text-xs uppercase text-muted-foreground", className)}>
        Awaiting layers
      </section>
    );
  }

  return (
    <section className={cn("relative flex h-full flex-col bg-background", className)}>
      <div className="absolute inset-0 dither-mask-sm dither-mask-invert pointer-events-none" />
      <div className="border-b border-border bg-black/70 px-ui-xs py-ui-xxs">
        <div className="flex items-center justify-between gap-ui-xs">
          <span className="text-[10px] font-bold uppercase text-muted-foreground">Layers</span>
          <span className="text-[10px] font-bold uppercase text-terminal">
            {activeLayerIds.length}/{layers.length}
          </span>
        </div>
      </div>
      <div className="grid min-h-0 flex-1 auto-rows-min grid-cols-1 gap-separator overflow-hidden bg-border">
      {layers.map((layer) => {
        const active = activeLayerIds.includes(layer.id);
        return (
          <Button
            active={active}
            className="min-w-0 justify-start rounded-none border-0 bg-background px-ui-xs py-ui-xxs"
            key={layer.id}
            onClick={() => onToggle(layer.id)}
            size="ui"
            type="button"
            variant={active ? "secondary" : "ghost"}
          >
            <span className={`size-2 shrink-0 ${dotClass[layer.tone]}`} />
            <span className="truncate text-[10px] uppercase">{layer.label}</span>
            <Divider orientation="vertical" variant="dotted" className="mx-ui-xxs h-5 text-border" />
            <span className="ml-auto font-mono text-[10px]">{layer.count}</span>
          </Button>
        );
      })}
      </div>
    </section>
  );
}
