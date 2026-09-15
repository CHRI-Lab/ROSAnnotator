# DataView and processing session contracts

This refactor is limited to data views and data processing sessions. The
frontend compatibility reference is the locally available
`origin/frontend-pannels-revamp` at `9c713d5`. Its panel layout is not copied;
its registry and context interfaces are preserved so these views can be used
by that workspace and by the current Annotator.

## DataView

`BaseDataView` declares the interface inherited by `VideoDataView`,
`TranscriptDataView`, `AnnotationDataView`, `AnnotationStatisticsDataView`, and
`TierStatisticsDataView`.

| Member | Input | Output |
| --- | --- | --- |
| `id`, `label` | — | Stable string identifier and display label |
| `render` | `ViewPanelContext` | `ReactElement` |
| `toDefinition` | — | `{ id, label, component: ComponentType<ViewPanelContext> }` |

`ViewPanelContext` carries `videoPath`, `transcript`, `played`, `isPlaying`,
`onProgress`, `onPlay`, `onPause`, `onSeek`, `onDurationChange`, and `playerRef`.
All numeric times are seconds within the currently loaded media. A video path
is relative to the processed-data directory; the player serves it under
`/processed/`. `playerRef` accepts a player or `null` on unmount. Progress, seek,
duration, play and pause callbacks return `void`.

The parent creates a stable component function for each instance, avoiding
player remounts when playback state updates. Subclass `render` methods return
elements; hooks belong inside the React components they render. The existing
five registry IDs, named component exports, `availableViews`, and type
re-exports remain available to Cassie's selector and panels. The current
Transcript ignores the forwarded `isPlaying` prop; the revamped Transcript
can consume it through the same adapter.

To add a view, extend `BaseDataView`, implement `id`, `label`, and `render`, and
add one instance to `dataViewDefinitions`. No selector changes are required.

## Data processing session

`RosbagProcessingSession` and `ChunkProcessingSession` inherit
`BaseDataProcessingSession`. Callers invoke the parent's
`process(request: ProcessingRequest) -> ProcessingResult`. Subclasses implement
hooks instead of overriding `process`.

| Hook | Input | Output / behavior |
| --- | --- | --- |
| `_validate` | `ProcessingRequest` | `None`; raise on invalid input |
| `_load_cached` | `ProcessingRequest` | `ProcessingResult`, or `None` for a cache miss |
| `_run` | `ProcessingRequest` | Fresh `ProcessingResult`; abstract |
| `_finalize` | Request and result | Result with session metadata |
| `_validate_result` | Result | `None`; reject invalid common fields with `TypeError` |

The parent runs these stages in order, skipping `_run` for a cache hit and
validating the result for both paths. ROS/ML processing errors propagate to
the existing HTTP adapters, which retain their error/status mappings.

### Request

- `bag_path`: nonempty string path to the input bag.
- `processed_root`: output directory; defaults to `/app/processed_data`.
- `booklist_filename`, `annotation_filename`: optional whole-bag metadata files.
- `manifest_id`, `chunk`: required for chunk sessions, absent for whole-bag sessions.
- `chunk`: `index` (nonnegative integer), `start_seconds`, `end_seconds`
  (finite, nonnegative start and end greater than start), plus optional
  duration, navigation and status metadata.

The existing `process_chunk(...)` adapter supplies
`/app/processed_data/chunks` as its default output root. Direct chunk session
callers should supply that root explicitly. The dataclass fields are frozen;
callers should also treat the nested chunk dictionary as read-only.

### Result

Every session returns these common fields:

| Field | Type / meaning |
| --- | --- |
| `video_path` | String, relative to `/app/processed_data` |
| `audio_path`, `waveform_image_path` | Relative path string, or `None` when unavailable |
| `audio_transcript` | String in the existing timestamped transcript format |
| `speaker_data` | List of segments with numeric `start_time`/`end_time`, string `speaker_label`/`text` |

Whole-bag sessions also return `booklist_data`, `annotation_data`, and the
existing `message`. Fresh results save structured speakers alongside the
transcript; subsequent cache reads return them. Older caches without that
sidecar return an empty speaker list without rerunning transcription.

Chunk sessions retain the original chunk fields and `status: "ready"`.
The chunk HTTP adapter continues to attach manifest information, codebook and
rebased annotations. Chunk bounds refer to bag start; transcript, speaker and
annotation positions refer to the current chunk's media. Existing API URLs,
chunk cache layout, locking and HTTP error handling remain in place.

Whole-bag video frames/FPS are kept on the session and copied by the HTTP
adapter to the globals used by existing chat code. This preserves that
integration; it does not introduce isolated chat state for concurrent users.

## Verification

From `src/backend` (standard library only, media operations mocked):

```sh
python -m unittest tests.test_processing_sessions -v
```

From `src/frontend`:

```sh
node tests/dataViews.test.cjs
node tests/autosave.test.cjs
npm run build
```

The view tests exercise the actual classes and registry with UI/media leaves
stubbed. They check compatibility, stable component identity, URL generation
and playback/seek callbacks. Session tests cover fresh/cache equivalence,
legacy caches, input/output validation, errors and video resource release.
The Django API tests in `rosbag_processing.tests` require the backend runtime.

At implementation time, 10 session tests, 4 view tests and 4 existing autosave
tests passed. Vite production bundling also passed. The full frontend build was
blocked by 18 pre-existing TypeScript diagnostics; comparison against HEAD
found no added diagnostics. Django/ROS integration and browser media playback
still require validation in the backend runtime (Django was unavailable and
the local Docker daemon was not running).
