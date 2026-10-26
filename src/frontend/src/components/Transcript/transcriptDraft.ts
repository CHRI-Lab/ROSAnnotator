import type { SpeakerSegment } from "../../types/annotations";

export type TranscriptDraft = Omit<SpeakerSegment, "start_time" | "end_time"> & {
  start_time: string;
  end_time: string;
};

export const createTranscriptDraft = (segments: SpeakerSegment[]): TranscriptDraft[] =>
  segments.map(segment => ({ ...segment, start_time: String(segment.start_time), end_time: String(segment.end_time) }));

export const parseTranscriptDraft = (draft: TranscriptDraft[], duration: number): SpeakerSegment[] => {
  if (!Number.isFinite(duration) || duration <= 0) throw new Error("The transcript duration is unavailable.");
  return draft.map((segment, index) => {
    const start = Number(segment.start_time), end = Number(segment.end_time);
    if (!segment.start_time.trim() || !segment.end_time.trim() || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start || end > duration) {
      throw new Error(`Segment ${index + 1}: enter start/end seconds within 0 to ${duration}, with end at or after start.`);
    }
    if (!segment.speaker_label.trim() || /[\r\n]/.test(segment.speaker_label)) {
      throw new Error(`Segment ${index + 1}: enter a nonempty, single-line speaker label.`);
    }
    return { ...segment, speaker_label: segment.speaker_label.trim(), start_time: start, end_time: end };
  });
};

export const renameTranscriptSpeaker = (draft: TranscriptDraft[], from: string, to: string): TranscriptDraft[] =>
  draft.map(segment => segment.speaker_label.trim() === from.trim() ? { ...segment, speaker_label: to.trim() } : segment);
