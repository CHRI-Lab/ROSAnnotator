import type { AnnotationBlock, AxisData } from "../../types/annotations";

export const clampTimeToDuration = (value: number, duration: number): number => {
  if (!Number.isFinite(value)) return 0;
  if (!Number.isFinite(duration) || duration < 0) return Math.max(0, value);
  return Math.min(duration, Math.max(0, value));
};

export const clampBlockToDuration = (
  block: AnnotationBlock,
  duration: number,
): AnnotationBlock => {
  const start = clampTimeToDuration(block.start, duration);
  const end = Math.max(start, clampTimeToDuration(block.end, duration));
  return { ...block, start, end };
};

export const clampAxesToDuration = (
  axes: AxisData[],
  duration: number,
): AxisData[] => axes.map((axis) => ({
  ...axis,
  blocks: (axis.blocks ?? []).map((block) => clampBlockToDuration(block, duration)),
}));
