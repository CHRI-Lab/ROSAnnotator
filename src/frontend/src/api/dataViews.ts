import type { BackendDataView } from '../components/FrontEndWorkspace/viewTypes';
import type { AIRecord } from '../types/aiRecords';
import type {
  AnnotationAxisPayload,
  BookList,
  SpeakerSegment,
} from '../types/annotations';

export type AnnotationSourceCheck = {
  status: "ok" | "mismatch" | "unknown";
  name_differs: boolean;
  duration_differs: boolean;
  recorded_bag_filename: string | null;
  recorded_duration: number | null;
  loaded_bag_filename: string | null;
  loaded_duration: number | null;
  annotation_end_seconds: number;
  overflows: boolean;
  overflow_block_count: number;
  orphan_block_count: number;
};

export type ViewPayload = {
  duration_seconds?: number;
  annotation_source_check?: AnnotationSourceCheck | null; 
  video_path: string;
  audio_path: string | null;
  audio_transcript: string;
  waveform_image_path: string | null;
  speaker_data: SpeakerSegment[];
  booklist_data: BookList;
  annotation_data: AnnotationAxisPayload[] | null;
  ai_records?: AIRecord[];
  chat_context_id?: string;
  views: Record<string, BackendDataView>;
  [key: string]: unknown;
};

// Discover processors from the backend: adding a view never changes this loader.
export async function loadDataViews(
  url: string, body: Record<string, unknown>, onProgress?: (payload: ViewPayload) => void,
): Promise<ViewPayload> {
  const catalogResponse = await fetch('http://localhost:8000/api/views/');
  if (!catalogResponse.ok) throw new Error('Unable to load the data view registry.');
  const catalog: { views: { view_id: string }[] } = await catalogResponse.json();
  let result: ViewPayload = {
    video_path: '', audio_path: null, waveform_image_path: null, audio_transcript: '',
    speaker_data: [], booklist_data: {}, annotation_data: null,
    views: Object.fromEntries(catalog.views.map(({ view_id }) => [view_id, {
      view_id, available: false, status: 'loading', reason: null, selected_topics: [], duration: 0,
      time_origin: { reference: 'bag_start', bag_offset_seconds: 0, absolute_seconds: 0 },
      processed_data: null, warnings: [],
    }])),
  };
  await Promise.all(catalog.views.map(async ({ view_id }) => {
    try {
      const response = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, view_ids: [view_id] }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : 'View request failed.');
      if (!payload.views?.[view_id]) throw new Error('The requested view was not returned.');
      // Each request owns its own view status. Dependencies may finish elsewhere.
      const updates = Object.fromEntries(Object.entries(payload).filter(([key, value]) =>
        !['views', 'status', 'error'].includes(key) && value != null && value !== '' &&
        (!Array.isArray(value) || value.length > 0)));
      result = { ...result, ...updates, views: { ...result.views, [view_id]: payload.views[view_id] } };
    } catch (error) {
      result = { ...result, views: { ...result.views, [view_id]: {
        ...result.views[view_id], status: 'failed', reason: String(error), available: false,
      } } };
    }
    onProgress?.(result);
  }));
  return result;
}
