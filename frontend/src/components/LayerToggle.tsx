import type { LayerViewModel } from "@/lib/layers";

interface LayerToggleProps {
  layers: LayerViewModel[];
  activeLayerIds: string[];
  onToggle: (layerId: string) => void;
}

export function LayerToggle({ layers, activeLayerIds, onToggle }: LayerToggleProps) {
  return (
    <section className="rounded-[1.6rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-4 shadow-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.34em] text-[#b8c1bd]">Layer Controls</p>
          <p className="mt-2 text-sm leading-6 text-white/55">
            Toggle response layers before they are projected onto the tactical surface.
          </p>
        </div>
        <div className="text-[11px] uppercase tracking-[0.24em] text-white/38">
          {activeLayerIds.length} active / {layers.length} total
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {layers.length > 0 ? (
          layers.map((layer) => {
            const active = activeLayerIds.includes(layer.id);
            return (
              <button
                key={layer.id}
                type="button"
                onClick={() => onToggle(layer.id)}
                className={`rounded-full border px-4 py-3 text-[11px] uppercase tracking-[0.26em] transition ${
                  active
                    ? "border-[#8ff6d2]/35 bg-[#8ff6d2]/10 text-[#e8fff6]"
                    : "border-white/10 bg-black/10 text-white/48 hover:text-white/78"
                }`}
              >
                {layer.type} / {layer.itemCount}
              </button>
            );
          })
        ) : (
          <div className="rounded-full border border-dashed border-white/10 px-4 py-3 text-[11px] uppercase tracking-[0.26em] text-white/40">
            No response layers yet
          </div>
        )}
      </div>
    </section>
  );
}
