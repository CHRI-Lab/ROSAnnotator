import {
  AnnotationDataView,
  AnnotationStatisticsDataView,
  AudioDataView,
  TierStatisticsDataView,
  TranscriptDataView,
  VideoDataView,
  WaveformDataView,
  WrenchDataView,
} from "./dataViews";
import type { BackendDataView, DataViewDefinition } from "./viewTypes";

export const availableViews: DataViewDefinition[] = [
  new VideoDataView().toDefinition(),
  new TranscriptDataView().toDefinition(),
  new AnnotationDataView().toDefinition(),
  new AnnotationStatisticsDataView().toDefinition(),
  new TierStatisticsDataView().toDefinition(),
  new AudioDataView().toDefinition(),
  new WaveformDataView().toDefinition(),
  new WrenchDataView().toDefinition(),
];

export function viewsWithAvailability(views?: Record<string, BackendDataView>) {
  return availableViews.map(view => ({
    ...view,
    available: views ? views[view.id]?.status === 'ready' && views[view.id]?.available === true && views[view.id]?.processed_data != null : true,
    reason: views?.[view.id]?.reason ?? (views && !views[view.id] ? 'No data returned for this view.' : null),
    status: views?.[view.id]?.status,
  }));
}

export type { DataViewDefinition, ViewPanelContext } from "./viewTypes";
