import type { SpeakerSegment } from "../../types/annotations";

type TimeRange = { start: number; end: number };

const timestamp = (seconds: number) => {
  const wholeSeconds = Math.floor(seconds);
  const minutes = Math.floor(wholeSeconds / 60);
  const remainder = wholeSeconds % 60;
  return `[${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}]`;
};

/** Build the transcript evidence that overlaps the selected chunk-local range. */
export const transcriptForTimeRange = (
  transcript: string,
  segments: SpeakerSegment[],
  range?: TimeRange,
) => {
  if (!range || segments.length === 0) return transcript;
  return segments
    .filter((segment) => segment.start_time < range.end && segment.end_time > range.start)
    .map((segment) => (
      `${timestamp(segment.start_time)} Speaker ${segment.speaker_label}: `
      + `${segment.text.replace(/[\r\n]+/g, " ")} ${timestamp(segment.end_time)}`
    ))
    .join("\n");
};
