import ReactPlayer from "react-player";

import AnnotationTable from "../AnnotationTable";
import StatisticsAnnotation from "../StatisticsAnnotation";
import StatisticsTier from "../StatisticsTier";
import Transcript from "../Transcript";
import { ViewPanelContext } from "./viewTypes";

export const VideoView = ({
  videoPath,
  onDurationChange,
  onProgress,
  playerRef,
}: ViewPanelContext) => (
  <ReactPlayer
    ref={playerRef}
    width="100%"
    height="auto"
    url={`/processed/${videoPath}`}
    onDuration={onDurationChange}
    onProgress={({ playedSeconds }) => onProgress(playedSeconds)}
    controls
    playing
  />
);

export const TranscriptView = ({
  transcript,
  played,
  onSeek,
}: ViewPanelContext) => (
  <Transcript LRC={transcript} played={played} setPlayed={onSeek} />
);

export const AnnotationView = () => <AnnotationTable />;
export const AnnotationStatisticsView = () => <StatisticsAnnotation />;
export const TierStatisticsView = () => <StatisticsTier />;
