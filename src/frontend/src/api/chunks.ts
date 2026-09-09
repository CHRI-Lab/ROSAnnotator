const API_BASE = "http://localhost:8000/api";

export interface InputInspection {
  bag_filename: string;
  duration_seconds: number;
  duration_minutes: number;
  supports_chunking: boolean;
}

export interface VideoChunk {
  index: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  previous_index: number | null;
  next_index: number | null;
  status: "not_processed" | "ready";
}

export interface ChunkManifest {
  id: string;
  bag_filename: string;
  chunking_enabled: boolean;
  duration_seconds: number;
  chunk_seconds: number;
  chunk_count: number;
  chunks: VideoChunk[];
}

export interface ChunkResult extends VideoChunk {
  manifest_id: string;
  bag_filename: string;
  time_reference: "bag_start";
  video_path: string;
  audio_path: string | null;
  waveform_image_path: string | null;
  audio_transcript: string;
  speaker_data: Array<unknown>;
  booklist_data: unknown;
  annotation_data: unknown;
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.error ?? Object.values(payload).flat().join(" ");
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return payload as T;
}

export async function inspectInput(bagFilename: string): Promise<InputInspection> {
  const response = await fetch(`${API_BASE}/inputs/inspect/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bag_filename: bagFilename }),
  });
  return readJson<InputInspection>(response);
}

export async function createChunkManifest(options: {
  bagFilename: string;
  booklistFilename?: string;
  annotationFilename?: string;
  chunkingEnabled: boolean;
  chunkSeconds?: number;
}): Promise<ChunkManifest> {
  const response = await fetch(`${API_BASE}/chunks/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bag_filename: options.bagFilename,
      booklist_filename: options.booklistFilename || "",
      annotation_filename: options.annotationFilename || "",
      chunking_enabled: options.chunkingEnabled,
      ...(options.chunkingEnabled ? { chunk_seconds: options.chunkSeconds } : {}),
    }),
  });
  return readJson<ChunkManifest>(response);
}

export async function getChunkManifest(manifestId: string): Promise<ChunkManifest> {
  const response = await fetch(`${API_BASE}/chunks/${manifestId}/`);
  return readJson<ChunkManifest>(response);
}

export async function processChunk(
  manifestId: string,
  chunkIndex: number
): Promise<ChunkResult> {
  const response = await fetch(
    `${API_BASE}/chunks/${manifestId}/${chunkIndex}/process/`,
    { method: "POST" }
  );
  return readJson<ChunkResult>(response);
}
