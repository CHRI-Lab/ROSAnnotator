import { ComponentType } from "react";
import ReactPlayer from "react-player";

export type ViewPanelContext = {
  videoPath: string;
  transcript: string;
  played: number;
  isPlaying: boolean;
  onProgress: (time: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (time: number) => void;
  onDurationChange: (duration: number) => void;
  playerRef: (player: ReactPlayer | null) => void;
};

export type DataViewDefinition = {
  id: string;
  label: string;
  component: ComponentType<ViewPanelContext>;
};
