import ReactPlayer from "react-player";
import { useEffect, useRef } from 'react';

import AnnotationTable from "../AnnotationTable";
import StatisticsAnnotation from "../StatisticsAnnotation";
import StatisticsTier from "../StatisticsTier";
import Transcript from "../Transcript";
import { BaseDataView } from "./BaseDataView";
import type { ViewPanelContext } from "./viewTypes";

const CompanionAudio = ({ audioPath, played, isPlaying }: ViewPanelContext) => {
  const player = useRef<ReactPlayer | null>(null);
  useEffect(() => {
    if (player.current && Math.abs(player.current.getCurrentTime() - played) > 0.25) {
      player.current.seekTo(played, 'seconds');
    }
  }, [played]);
  return <ReactPlayer ref={player} url={`/processed/${audioPath}`} playing={isPlaying}
    width={0} height={0} onReady={instance => instance.seekTo(played, 'seconds')} />;
};

const VideoContent = (context: ViewPanelContext) => {
  const {
  videoPath,
  onDurationChange,
  onProgress,
  isPlaying,
  onPlay,
  onPause,
  playerRef,
  } = context;
  const player = (
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
    onReady={instance => instance.seekTo(context.played, 'seconds')}
  />
  );
  return context.audioPath && context.views?.video?.processed_data?.has_audio === false
    ? <>{player}<CompanionAudio {...context} /></> : player;
};

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

export class AudioDataView extends BaseDataView {
  readonly id = 'audio';
  readonly label = 'Audio';
  render(context: ViewPanelContext): React.ReactElement {
    // Video includes audio when available; use one playback source at a time.
    return context.videoPath
      ? <span>Audio plays with the video.</span>
      : <VideoContent {...context} videoPath={context.audioPath || ''} />;
  }
}

export class WaveformDataView extends BaseDataView {
  readonly id = 'waveform';
  readonly label = 'Waveform';
  render(context: ViewPanelContext): React.ReactElement {
    return <img style={{ width: '100%' }} src={`/processed/${context.waveformPath}`} alt="Audio waveform" />;
  }
}

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
  new AudioDataView().toDefinition(), new WaveformDataView().toDefinition(),
];

// Preserve Cassie's existing named component exports.
export const VideoView = video.component;
export const TranscriptView = transcript.component;
export const AnnotationView = annotations.component;
export const AnnotationStatisticsView = annotationStatistics.component;
export const TierStatisticsView = tierStatistics.component;
