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

export const TranscriptView = ({
  transcript,
  played,
  isPlaying,
  onSeek,
}: ViewPanelContext) => (
  <Transcript
    LRC={transcript}
    played={played}
    isPlaying={isPlaying}
    setPlayed={onSeek}
  />
);

export const AnnotationView = () => <AnnotationTable />;
export const AnnotationStatisticsView = () => <StatisticsAnnotation />;
export const TierStatisticsView = () => <StatisticsTier />;
