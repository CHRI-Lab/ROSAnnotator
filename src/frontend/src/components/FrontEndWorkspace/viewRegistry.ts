import {
  AnnotationStatisticsView,
  AnnotationView,
  TierStatisticsView,
  TranscriptView,
  VideoView,
} from "./dataViews";
import { DataViewDefinition } from "./viewTypes";

export const availableViews: DataViewDefinition[] = [
  { id: "video", label: "Video", component: VideoView },
  { id: "transcript", label: "Transcript", component: TranscriptView },
  { id: "annotations", label: "Annotations", component: AnnotationView },
  {
    id: "statistics-annotations",
    label: "Statistics (Annotations)",
    component: AnnotationStatisticsView,
  },
  {
    id: "statistics-tiers",
    label: "Statistics (Tiers)",
    component: TierStatisticsView,
  },
];

export type { DataViewDefinition, ViewPanelContext } from "./viewTypes";
