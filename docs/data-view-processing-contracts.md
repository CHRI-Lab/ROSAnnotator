# Data-view processing contracts

See [the implementation design diagram](design-diagram.md).

## Extension points

Add a `DataViewProcessor` child, register it in `view_registry.PROCESSORS`, and
add a frontend `BaseDataView` component to `availableViews` in
`viewRegistry.ts`. No changes to
`process_views`, the HTTP workflow, the loader, or the tab renderer are required.

The backend parent defines `supported_message_types`, `check_availability`,
`extract`, `preprocess`, and `serialize`. `dependencies` declare shared inputs;
the workflow resolves their order. A processor may treat a dependency as optional
(video remains usable if audio fails). `legacy_fields` adapts existing response
fields without adding view-specific branches to the workflow.

Registered views are audio, video, transcript, waveform, annotations,
statistics-annotations, statistics-tiers, and wrench. All eight frontend
registry IDs, the existing named component exports, and the shared playback/seek
context remain supported.
The annotation/statistics processors describe an editable timeline; its live data
continues to come from `AxesProvider`. Imported annotations are attached after
processing, and the existing annotation/speaker/recovery initialization is retained.

## Reader and time contract

`RosbagReader` owns ROS metadata access, iteration, and safe closing. Loading
inspects topic names, ROS types, and message counts. Unsupported ROS types are
ignored. The default input is the first nonempty compatible topic in sorted name
order; `view_options[view_id].topics` can explicitly select one compatible topic.
No ROS topic name is hard-coded.
Wrench overrides the single-topic default and select all compatible
nonempty topics unless an explicit subset is requested.

A finite, positive `header.stamp` inside the bag time range takes precedence.
Otherwise the bag-record timestamp is used and a warning is recorded. Invalid
record times are skipped. Chunk filtering follows the selected timestamp, not
an earlier filter on bag-record time. Chunk ends are exclusive except at the
final bag endpoint. All output times are seconds relative to the bag or chunk
origin, and `bag_offset_seconds` allows conversion back to the bag timeline.

Extracted references are stably ordered by timestamp. Equal-time audio packets
retain their original order; equal-time images use the last image for playback,
while all original frame timestamps/IDs remain in response metadata. Video frame
durations follow the normalized timestamps; an initial image gap holds the first
image, and audio is padded with initial silence. Encoded audio packets are joined
as a stream, as in the existing MP3 input contract; packet timestamps are not PCM
sample timestamps. Arbitrary packet loss/gaps are not reconstructed.

Image processors preserve frame IDs and reject mixed nonempty coordinate frames
or a mismatch with an explicitly requested `frame_id`. They do not silently mix
coordinate systems or pretend to perform a spatial transformation.

## Response contract

Each `views[view_id]` contains:

| Field | Meaning |
| --- | --- |
| `view_id` | Stable registry ID |
| `status` | `ready`, `unavailable`, or `failed`; frontend additionally uses `loading` |
| `available` | True only after usable input and processing succeed |
| `reason` | Explanation for an unavailable/failed view |
| `selected_topics` | Selected ROS topic names |
| `duration` | Seconds within the bag or chunk |
| `time_origin` | `reference`, `bag_offset_seconds`, and `absolute_seconds` |
| `processed_data` | View-specific JSON, or null when unavailable |
| `warnings` | Timestamp fallbacks and other nonfatal issues |

The response preserves `video_path`, `audio_path`, `waveform_image_path`,
`audio_transcript`, `speaker_data`, `booklist_data`, `annotation_data`, and chunk
navigation fields. Missing video uses an empty string; missing audio/waveform
uses null. Media paths remain relative to `/app/processed_data`.

A failed view does not abort other views. No available views produces HTTP 200
with `status: unavailable`, per-view reasons, and
`error: {code: "no_available_views", message: "..."}`. Invalid HTTP input and
unreadable bags still use HTTP errors. Optional annotation/codebook read failures
are attached as warnings while usable media remains available.

## API and frontend loading

`GET /api/views/` publishes registered IDs and supported ROS types.
`POST /api/inputs/inspect/` includes topic metadata as well as duration.
Whole-bag and chunk processing accept optional `view_ids`; omitted means all
views. `view_options` is accepted for whole-bag requests and stored in chunk
manifests. For example:

```json
{"bag_filename":"sample.bag","view_ids":["video"],
 "view_options":{"video":{"topics":["/camera/color"],"frame_id":"camera"}}}
```

The frontend discovers the catalog and requests views concurrently. Each request
owns its view's loading/failure state. Successful video/audio can render before
transcription finishes. `ViewPanel` refuses to mount unavailable or null-data
views and contains rendering exceptions. Disabled tabs and notices show reasons;
a global data error dialog is used only if no usable views are returned.

One media player drives shared playback time and seek callbacks. Video includes
usable audio; if muxing fails, a companion audio player follows the same clock.
An audio player supplies the clock for audio-only inputs. The annotation editor
waits for initial data loading to finish. If recovery data exists, a modal blocks
editing and autosave remains disabled until the user restores or discards it.
Chunk switching still waits for autosave to flush and retains the current editor
on failure.

## Cache and migration

Caching lives in `ViewCache`, outside child processors. Keys include resolved bag
path, size, nanosecond mtime, view ID/version, selected topics, options, chunk
bounds, and dependency results. Only successful results are cached; failures can
be retried. Missing artifacts or invalid JSON cause a cache miss. Update a
processor's `cache_version` when its processing semantics change.

OS file locks serialize identical work and release on worker termination. Unique
temporary files plus atomic replacement publish results. Per-manifest chunk
`result.json` files now summarize status; reusable media is stored under
`views/<uuid6>/`. The UUID6 is the internal processed data-view identity; clients
treat any returned media path as opaque. A different manifest ID can reuse the
same processed views without changing playback behavior.
Manifest generation uses a UUID5 derived from the bag, chunk size, and source
identity, so the same input reuses one manifest and its recovery files. See
[chunked annotation saving](chunk-annotation-saving.md).

The former SHA-256 directories are checked only as a compatibility fallback, so
existing valid media remains playable and is not regenerated. New processed
data views are written exclusively to UUID6 directories. Older caches that lack
source/topic/options identity are left on disk and are not reused automatically.
Existing annotation exports and autosave files retain their layouts and scopes.

Whole-bag video responses return a `chat_context_id`; their selected frames and
conversation history are stored under that token in Django's cache. Chunk video
responses currently create a token with an empty frame list, so visual prompts
in chunked sessions do not receive extracted frames through this path. Requests
without a context token retain the legacy fallback to module-level frames and
history. Deployments with multiple workers should configure a shared Django
cache backend for token-scoped conversations; the default local-memory cache and
the legacy fallback are both process-local.

## Verification

From `src/backend` with Django/REST framework and HTTP dependencies installed:

```sh
python manage.py test rosbag_processing.tests tests.test_processing_sessions tests.test_data_view_processing tests.test_data_view_api tests.test_chunks tests.test_autosave tests.test_chunk_autosave
```

The reader/workflow tests also run without Django or ROS:

```sh
python -m unittest tests.test_processing_sessions tests.test_data_view_processing
```

From `src/frontend`:

```sh
node tests/dataViews.test.cjs
node tests/dataViewLoading.test.cjs
node tests/autosave.test.cjs
npm run build
```
