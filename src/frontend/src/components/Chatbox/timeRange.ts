export type AssistantTimeRange = {
  start: number;
  end: number;
};

export const formatChunkTime = (seconds: number) => {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
};

export const parseChunkTime = (value: string): number | null => {
  const match = value.trim().match(/^(\d+):([0-5]\d)$/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
};

export const validateChunkTimeRange = (
  startValue: string,
  endValue: string,
  duration: number,
): { range: AssistantTimeRange | null; error: string } => {
  const start = parseChunkTime(startValue);
  const end = parseChunkTime(endValue);
  if (start === null || end === null) {
    return { range: null, error: "Use MM:SS, for example 00:15." };
  }
  if (!Number.isFinite(duration) || duration <= 0) {
    return { range: null, error: "The current chunk duration is unavailable." };
  }
  if (start >= end) {
    return { range: null, error: "End time must be after start time." };
  }
  if (start < 0 || end > duration) {
    return {
      range: null,
      error: `Select a range within 00:00–${formatChunkTime(duration)}.`,
    };
  }
  return { range: { start, end }, error: "" };
};
