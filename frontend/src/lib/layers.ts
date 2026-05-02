import type { MapLayerPayload } from "@/types/findings";


export interface LayerViewModel {
  id: string;
  type: MapLayerPayload["type"];
  visible: boolean;
  itemCount: number;
}


export function toLayerViewModels(layers: MapLayerPayload[]): LayerViewModel[] {
  return layers.map((layer) => ({
    id: layer.id,
    type: layer.type,
    visible: layer.visible,
    itemCount: layer.data.length
  }));
}
