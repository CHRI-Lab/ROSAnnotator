export type AIInstructionStep = {
  action: string;
  parameters?: Record<string, unknown>;
};

export type AIInstruction = {
  type: "instruction";
  steps: AIInstructionStep[];
};

export type AssistantDataViewId =
  | "audio"
  | "video"
  | "transcript"
  | "waveform"
  | "annotations"
  | "statistics-annotations"
  | "statistics-tiers"
  | "codebook";

export type AssistantDataViewOption = {
  id: AssistantDataViewId;
  label: string;
};

export type AIRecord = {
  schema_version: number;
  run_id: string;
  timestamp: string;
  model_selection: {
    requested: string;
    used: string;
    context_routes: Record<string, unknown>;
  };
  model: Record<string, unknown>;
  parameters: Record<string, unknown>;
  prompts: {
    system?: string;
    user?: string;
  };
  ai_response: string;
  request_options?: {
    selected_data_types: AssistantDataViewId[];
    selected_timelines: Array<{
      axis_id: number;
      axis_name: string | null;
    }>;
    allow_new_timeline: boolean;
    selected_time_range: null | {
      chunk_relative_seconds: { start: number; end: number };
      whole_video_seconds: { start: number; end: number };
    };
    video_frames: {
      count: number;
      samples: Array<{
        frame_index: number;
        chunk_relative_seconds: number;
        whole_video_seconds: number;
        sha256: string;
      }>;
    };
    current_chunk: {
      index: number;
      start_seconds: number;
      end_seconds: number | null;
      is_chunked: boolean;
    };
  };
  [key: string]: unknown;
};

export type AssistantRequestOptions = {
  selectedDataViews?: AssistantDataViewId[];
  timeRange?: {
    start: number;
    end: number;
  };
  fallbackConsent?: {
    from: "local" | "remote";
    to: "local" | "remote";
    userConsented: true;
  };
  timelineScope?: {
    axisIds: number[];
    allowNew: boolean;
  };
};

export const buildAIRecordAnnotationName = (
  rosBagFileName: string,
  bookListFileName?: string,
) => `${rosBagFileName}+${bookListFileName || "noBookList"}`;
