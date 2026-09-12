# Video chunk backend API

All timestamps are seconds relative to the beginning of the ROSBag. Chunk media
and transcripts use timestamps relative to the beginning of that chunk; add
`start_seconds` when converting an annotation to the full-input timeline.

## Inspect input duration

`POST /api/inputs/inspect/`

```json
{"bag_filename": "example.bag"}
```

## Create a chunk manifest

Chunked input:

```http
POST /api/chunks/
```

```json
{
  "bag_filename": "example.bag",
  "chunking_enabled": true,
  "chunk_seconds": 300
}
```

The chunk duration must be shorter than the input. For an unchunked input, omit
`chunk_seconds` and send `"chunking_enabled": false`; the API returns one chunk
covering the complete input.

## Read navigation metadata

```http
GET /api/chunks/{manifest_id}/
GET /api/chunks/{manifest_id}/{chunk_index}/
```

Each chunk contains `previous_index`, `next_index`, and a `status` of
`not_processed` or `ready`. These fields support the dropdown and navigation
buttons without loading media.

## Process and load one chunk

```http
POST /api/chunks/{manifest_id}/{chunk_index}/process/
```

The first request extracts only that ROSBag time range and creates its video,
audio, waveform, transcript, and speaker data. Later requests return the cached
`result.json`. Concurrent processing of the same chunk returns HTTP 409.

Before switching chunks, the frontend must await the separate auto-save API and
only call this endpoint after saving succeeds:

```text
await autoSave(currentChunk)
await processAndLoad(targetChunk)
```

Chunk autosaves use the existing `/api/autosave/save/`, `check/`, `load/`, and
`delete/` endpoints. Supply both `manifest_id` (UUID) and `chunk_index` (integer
from 0 to 9999), in the POST body or query parameters. Omitting both retains
whole-bag autosave behavior. Recovery files are isolated by manifest and chunk
under `annotation/chunks/{manifest_id}/{chunk_index}/`; block times remain local
to the chunk. Empty axes and shortcut keys are retained.

The editor awaits pending saves and saves the latest edits before processing
the next chunk. Failed saves keep the current editor mounted; dismiss the error
and select the chunk again to retry. Loading a chunk, including reopening the
same manifest URL, restores its saved axes before mounting the timeline.
Creating a new manifest starts a separate recovery set.
