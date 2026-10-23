export interface AnnotationBlock {
  start: number;
  end: number;
  text?: string;
  // Present only while editing a block clipped by a chunk. These absolute
  // bounds let the backend preserve the unseen part of the original block.
  sourceStart?: number;
  sourceEnd?: number;
}

export interface AxisData {
  id: number;
  type: string;
  typeName?: string;
  axisName?: string;
  shortcutKey?: string;
  blocks: AnnotationBlock[];
}

export type BookList = Record<string, string[]>;

export interface AnnotationAxisPayload {
  id: number;
  axisType: string;
  axisName: string;
  axisBooklistName: string;
  annotationBlocks: AnnotationBlock[];
}

export interface SpeakerSegment {
  speaker_label: string;
  start_time: number;
  end_time: number;
  text: string;
}
