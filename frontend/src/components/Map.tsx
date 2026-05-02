import { ADSBLayer } from "@/components/layers/ADSBLayer";
import { SatelliteLayer } from "@/components/layers/SatelliteLayer";
import { StravaLayer } from "@/components/layers/StravaLayer";
import type { LayerViewModel } from "@/lib/layers";
import type { AnalyzeResponse } from "@/types/findings";

interface MapProps {
  report?: AnalyzeResponse | null;
  visibleLayerIds: string[];
  layers: LayerViewModel[];
}


export function Map({ report, visibleLayerIds, layers }: MapProps) {
  return (
    <section className="overflow-hidden rounded-[2rem] border border-white/10 bg-panel shadow-panel">
      <div className="border-b border-white/10 px-5 py-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-white/50">Map Surface</p>
            <h2 className="mt-2 text-xl font-semibold text-ink">
              {report ? report.target.name : "Awaiting target selection"}
            </h2>
          </div>
          <div className="text-right text-xs text-white/45">
            <div>deck.gl shell</div>
            <div>{layers.length} layers available</div>
          </div>
        </div>
      </div>
      <div className="grid min-h-[380px] place-items-center bg-[linear-gradient(135deg,rgba(120,240,200,0.08),transparent_30%),linear-gradient(180deg,#0f171a_0%,#0b1114_100%)] p-6">
        <div className="w-full max-w-3xl">
          <div className="grid gap-3 md:grid-cols-2">
            {visibleLayerIds.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-white/50">
                No layers enabled.
              </div>
            ) : null}
            {visibleLayerIds.some((id) => id.includes("strava")) ? <StravaLayer /> : null}
            {visibleLayerIds.some((id) => id.includes("adsb")) ? <ADSBLayer /> : null}
            {visibleLayerIds.some((id) => id.includes("satellite") || id.includes("footprint")) ? (
              <SatelliteLayer />
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
