import type { LayerViewModel } from "@/lib/layers";

interface LayerToggleProps {
  layers: LayerViewModel[];
  activeLayerIds: string[];
  onToggle: (layerId: string) => void;
}


export function LayerToggle({ layers, activeLayerIds, onToggle }: LayerToggleProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {layers.map((layer) => {
        const active = activeLayerIds.includes(layer.id);
        return (
          <button
            key={layer.id}
            type="button"
            onClick={() => onToggle(layer.id)}
            className={`rounded-full border px-3 py-2 text-xs uppercase tracking-[0.22em] transition ${
              active ? "border-accent bg-accent/15 text-accent" : "border-white/10 text-white/55"
            }`}
          >
            {layer.type} {layer.itemCount}
          </button>
        );
      })}
    </div>
  );
}
