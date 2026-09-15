import ReactPlayer from "react-player";

import AnnotationTable from "../AnnotationTable";
import StatisticsAnnotation from "../StatisticsAnnotation";
import StatisticsTier from "../StatisticsTier";
import Transcript from "../Transcript";
import { BaseDataView } from "./BaseDataView";
import type { ViewPanelContext } from "./viewTypes";

const VideoContent = ({
  videoPath,
  onDurationChange,
  onProgress,
  isPlaying,
  onPlay,
  onPause,
  playerRef,
}: ViewPanelContext) => (
  <ReactPlayer
    ref={playerRef}
    width="100%"
    height="auto"
    url={`/processed/${videoPath}`}
    onDuration={onDurationChange}
    onProgress={({ playedSeconds }) => onProgress(playedSeconds)}
    onPlay={onPlay}
    onPause={onPause}
    controls
    playing={isPlaying}
  />
);

const TranscriptContent = ({
  transcript,
  played,
  isPlaying,
  onSeek,
}: ViewPanelContext) => (
  <Transcript
    LRC={transcript}
    played={played}
    {...{ isPlaying }}
    setPlayed={onSeek}
  />
);

// Concrete views inherit the agreed render input/output from BaseDataView.
export class VideoDataView extends BaseDataView {
  readonly id = "video";
  readonly label = "Video";
  render(context: ViewPanelContext): React.ReactElement {
    return <VideoContent {...context} />;
  }
}

export class TranscriptDataView extends BaseDataView {
  readonly id = "transcript";
  readonly label = "Transcript";
  render(context: ViewPanelContext): React.ReactElement {
    return <TranscriptContent {...context} />;
  }
}

export class AnnotationDataView extends BaseDataView {
  readonly id = "annotations";
  readonly label = "Annotations";
  render(_context: ViewPanelContext): React.ReactElement {
    return <AnnotationTable />;
  }
}

export class AnnotationStatisticsDataView extends BaseDataView {
  readonly id = "statistics-annotations";
  readonly label = "Statistics (Annotations)";
  render(_context: ViewPanelContext): React.ReactElement {
    return <StatisticsAnnotation />;
  }
}

export class TierStatisticsDataView extends BaseDataView {
  readonly id = "statistics-tiers";
  readonly label = "Statistics (Tiers)";
  render(_context: ViewPanelContext): React.ReactElement {
    return <StatisticsTier />;
  }
}

// Construct definitions once so selectors and panels receive stable components.
const video = new VideoDataView().toDefinition();
const transcript = new TranscriptDataView().toDefinition();
const annotations = new AnnotationDataView().toDefinition();
const annotationStatistics = new AnnotationStatisticsDataView().toDefinition();
const tierStatistics = new TierStatisticsDataView().toDefinition();

export const dataViewDefinitions = [
  video, transcript, annotations, annotationStatistics, tierStatistics,
];

// Preserve Cassie's existing named component exports.
export const VideoView = video.component;
export const TranscriptView = transcript.component;
export const AnnotationView = annotations.component;
export const AnnotationStatisticsView = annotationStatistics.component;
export const TierStatisticsView = tierStatistics.component;
