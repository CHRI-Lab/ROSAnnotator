import type { AxisData, SpeakerSegment } from "../../types/annotations";

const normalizedName = (name: string) => name.trim().toLocaleLowerCase();

export const convertTranscriptToAnnotations = (
  axes: AxisData[],
  segments: SpeakerSegment[],
  duration: number,
  firstAxisId: number,
) => {
  const existingByName = new Map<string, AxisData[]>();
  axes.forEach((axis) => {
    const key = normalizedName(axis.axisName || "");
    existingByName.set(key, [...(existingByName.get(key) || []), axis]);
  });
  const speakerAxes = new Map<string, AxisData>();
  const replacements = new Map<number, AxisData>();
  const newAxes: AxisData[] = [];
  const skippedNames = new Set<string>();
  const seenSegments = new Set<string>();
  let skippedSegments = 0;
  let addedBlocks = 0;
  let nextAxisId = axes.reduce((next, axis) => Math.max(next, axis.id + 1), firstAxisId);

  for (const segment of segments) {
    const speakerName = segment.speaker_label.trim() || "Unknown Speaker";
    const key = normalizedName(speakerName);
    const existing = existingByName.get(key) || [];
    // A saved speaker axis can be empty in this chunk. Reuse it, but preserve
    // populated axes (including edits) and axes with incompatible codebooks.
    if (existing.length && (
      existing.length > 1 || existing[0].blocks.length > 0 ||
      normalizedName(existing[0].type) !== "type-in"
    )) {
      skippedNames.add(key);
      continue;
    }
    const { start_time: start, end_time: end } = segment;
    if (
      !Number.isFinite(duration) || duration <= 0 ||
      !Number.isFinite(start) || !Number.isFinite(end) ||
      start < 0 || end < start || end > duration
    ) {
      skippedSegments += 1;
      continue;
    }
    // Some transcripts repeat an identical segment. Keep only one copy.
    const segmentKey = JSON.stringify([key, start, end, segment.text]);
    if (seenSegments.has(segmentKey)) continue;
    seenSegments.add(segmentKey);
    let axis = speakerAxes.get(key);
    if (!axis) {
      if (existing.length) {
        axis = { ...existing[0], blocks: [] };
        replacements.set(axis.id, axis);
      } else {
        axis = { id: nextAxisId++, type: "Type-in", axisName: speakerName, blocks: [] };
        newAxes.push(axis);
      }
      speakerAxes.set(key, axis);
    }
    axis.blocks.push({ start, end, text: segment.text });
    addedBlocks += 1;
  }

  speakerAxes.forEach((axis) => axis.blocks.sort((a, b) => a.start - b.start));
  return {
    axes: addedBlocks ? [...axes.map((axis) => replacements.get(axis.id) || axis), ...newAxes] : axes,
    nextAxisId,
    addedAxes: newAxes.length,
    reusedAxes: replacements.size,
    addedBlocks,
    skippedSpeakers: skippedNames.size,
    skippedSegments,
  };
};
