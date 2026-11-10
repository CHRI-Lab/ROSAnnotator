import { ComponentType } from "react";
import ReactPlayer from "react-player";

export type ViewPanelContext = {
  videoPath: string;
  audioPath?: string | null;
  waveformPath?: string | null;
  views?: Record<string, BackendDataView>;
  transcript: string;
  onEditTranscript?: () => void;
  played: number;
  isPlaying: boolean;
  onProgress: (time: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (time: number) => void;
  onDurationChange: (duration: number) => void;
  playerRef: (player: ReactPlayer | null) => void;
};

export type BackendDataView = {
  view_id: string;
  status: 'loading' | 'ready' | 'unavailable' | 'failed';
  available: boolean;
  reason: string | null;
  selected_topics: string[];
  duration: number;
  time_origin: { reference: 'bag_start' | 'chunk_start'; bag_offset_seconds: number; absolute_seconds: number };
  processed_data: Record<string, unknown> | null;
  warnings: string[];
};

export type DataViewDefinition = {
  available?: boolean;
  reason?: string | null;
  status?: BackendDataView["status"];
  id: string;
  label: string;
  component: ComponentType<ViewPanelContext>;
};
