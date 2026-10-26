import type { ViewPayload } from "./dataViews";
import type { BackendDataView } from "../components/FrontEndWorkspace/viewTypes";
import type { SpeakerSegment } from "../types/annotations";

export type TranscriptEditRef = { scope: "whole" | "chunks"; key: string };
export type SavedTranscript = {
  view: BackendDataView;
  audio_transcript: string;
  speaker_data: SpeakerSegment[];
};

export const transcriptEditRef = (view?: BackendDataView): TranscriptEditRef | null => {
  const ref = view?.processed_data?.edit_ref as Partial<TranscriptEditRef> | undefined;
  return ref && (ref.scope === "whole" || ref.scope === "chunks") && typeof ref.key === "string" && /^(?:[a-f0-9]{64}|[a-f0-9]{8}-[a-f0-9]{4}-6[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})$/.test(ref.key)
    ? { scope: ref.scope, key: ref.key } : null;
};

export const applySavedTranscript = (data: ViewPayload, saved: SavedTranscript | null): ViewPayload => {
  const currentRef = transcriptEditRef(data.views?.transcript);
  const savedRef = saved && transcriptEditRef(saved.view);
  if (!saved || !currentRef || !savedRef || currentRef.scope !== savedRef.scope || currentRef.key !== savedRef.key ||
      Number(data.views.transcript.processed_data?.revision ?? 0) > Number(saved.view.processed_data?.revision ?? 0)) return data;
  return { ...data, audio_transcript: saved.audio_transcript, speaker_data: saved.speaker_data,
    views: { ...data.views, transcript: saved.view } };
};

export const saveTranscript = async (ref: TranscriptEditRef, revision: number, segments: SpeakerSegment[]): Promise<SavedTranscript> => {
  const response = await fetch(`http://localhost:8000/api/transcripts/${ref.scope}/${ref.key}/`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision, speaker_data: segments }),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.error || "Unable to save the transcript. Please retry.");
  if (!result?.view || !Array.isArray(result.speaker_data) || typeof result.audio_transcript !== "string") {
    throw new Error("The server returned an invalid transcript response.");
  }
  return result;
};
