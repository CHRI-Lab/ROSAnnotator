# Chunked annotation saving

See [data-view processing contracts](data-view-processing-contracts.md) for the
view pipeline these saves sit alongside.

## Key features

- An annotation CSV always holds **whole-recording time**, regardless of which
  chunk it was saved from.
- Saving from a chunk **merges** into the existing file: it replaces that
  chunk's contribution and leaves every other chunk's annotations untouched.
- Saving is **confirmed before it changes an existing file**, with the change
  described in terms of the chunk being saved.
- Annotation filenames are **validated server-side** before any path is built.
- The save dialog **defaults to the file in use**, so a save returns to the file
  it came from.
- Manifest IDs are **derived, not random**, so the same input reuses one
  manifest, one processed-view cache, and one set of recovery files.

---

## Time reference

Two frames exist and must not be confused.

| Context | Reference |
| --- | --- |
| Annotation CSV on disk | Seconds from bag start |
| Axes in the editor, chunked session | Seconds from chunk start |
| Axes in the editor, whole-recording session | Seconds from bag start |

`view_metadata.annotations_for_chunk` converts on load by subtracting
`chunk['start_seconds']`. `views.merge_chunk_annotations` converts back on save.
Any path that writes editor state to a CSV without that conversion stores
chunk-local times where absolute times are expected, and the error is silent:
the file parses, and the annotations sit at the wrong point in the recording.

## Chunk boundaries

When chunk configuration is confirmed with an imported annotation file, the
backend loads the annotation CSV and permanently splits every block that crosses
a confirmed chunk boundary.

The split annotation file is saved before the chunk manifest is created and
before the first chunk is processed or loaded into the workspace.

For example, with 60-second chunks, a block from 50–70 s becomes two independent
CSV records:

- 50–60 s
- 60–70 s

A block crossing multiple chunk boundaries is split at every boundary. Blocks
that already start or end at a boundary are not split again.

Each resulting record is independent. Editing or deleting the 50–60 (60-70) s record
does not modify or delete the 60–70 (50-60) s record.

This operation updates the imported annotation CSV directly. It does not use or
depend on chunk autosaves.

When a chunk is loaded, its annotation records are converted from
whole-recording timestamps to chunk-local timestamps. For example, the absolute
60–70 s record is displayed as 0–10 s in the second 60-second chunk.

## Merge

`views.merge_chunk_annotations(existing, incoming, chunk)` replaces the saved
annotation records belonging to the current chunk:

1. Keep every existing record outside the current chunk unchanged.
2. Remove the existing records displayed in the current chunk.
3. Convert the current editor records from chunk-local time to whole-recording
   time by adding the chunk start offset.
4. Add the converted records back to the complete annotation set.
5. Sort each axis by start time and renumber axis IDs from 1.

If a displayed record is absent from the incoming editor data, it is treated as
deleted. Because boundary-crossing annotations were already split into separate
records, this deletion affects only the record in the current chunk.

Axes are matched using `(axisName, axisType)`. Numeric axis IDs are not used as
stable identity because the editor may reassign them between loads, sessions,
or chunks.

IDs are renumbered when writing because `data_utils.load_annotation` groups CSV
rows by ID. Reusing the same ID for different axes could incorrectly combine
them.

The complete annotation CSV is written through a temporary file followed by
`os.replace`. The existing file is replaced only after the new file has been
written successfully, preventing a partial write from truncating the saved
annotations.

## Save request

`POST /api/save_annotation/`

| Field | Meaning |
| --- | --- |
| `annotation_name` | Filename stem; `.csv` is appended by the view |
| `annotation_data` | Axes and blocks, in the editor's current reference frame |
| `confirm_overwrite` | Proceed despite a reported conflict |
| `manifest_id` | Chunk scope; required with `chunk_index` |
| `chunk_index` | Chunk scope; required with `manifest_id` |
| `bag_filename` | Optional source ROSBag filename recorded in the CSV |
| `source_duration` | Optional whole-recording duration recorded in the CSV |

Chunk bounds are read from the manifest rather than sent by the client, so a
save cannot disagree with the range the loader used.

Responses:

| Status | Meaning |
| --- | --- |
| 200 | Written |
| 400 | Validation failed, including an invalid or out-of-range chunk index |
| 404 | Named manifest file does not exist |
| 409 | Would change an existing file; body describes what |
| 500 | Write failed |

A 409 body carries `reason` and the counts the prompt needs:

| `reason` | Condition |
| --- | --- |
| `file_exists` | Whole-recording save over an existing file |
| `chunk_is_empty` | File exists with no annotations in this chunk's range |
| `chunk_has_annotations` | File exists with annotations in this chunk's range |
| `file_unreadable` | File exists and cannot be parsed |

The client prompts and resends with `confirm_overwrite: true`. Attempting the
write and letting the server refuse avoids the gap a separate existence check
would leave between asking and acting.

Counts in a chunk conflict are produced with `clip_to_chunk`, so the prompt
describes exactly the set the merge will replace.

`file_unreadable` is reported rather than silently replaced. Annotation
filenames are user-chosen and nothing binds a CSV to this application, so the
target may not be an annotation file at all.

## Filename validation

`serializers.SaveAnnotationSerializer` rejects, before any path is constructed:

- names that are not their own basename, which blocks traversal
- `\ / : * ? " < > |` and the null byte
- names consisting only of dots or spaces, and names ending in either
- Windows reserved device names (`CON`, `LPT1`, and so on)
- names exceeding the 255-byte filesystem limit once `.csv` is appended

A trailing `.csv` is stripped rather than rejected, so a name pasted with its
extension does not become `name.csv.csv`.

`annotation_data` is validated structurally. Block times must be finite: Python's
`json` accepts `NaN` and `Infinity`, either of which would be written to the CSV
and then fail to parse on the way back.

The browser check in `saveUtils.isValidAnnotationName` remains, as a faster and
friendlier first pass. It is not the enforcement point, since the endpoint can
be called directly.

## Filename in use

The save dialog defaults to, in order: the annotation file loaded for this
session, the name last saved during it, then a name generated from the bag and
codebook.

The name is held in `MainPage`. Both `Annotator` and `Timeline` are keyed by
chunk and remount on every chunk switch, so anything held there would be lost.

This is not only convenience. A chunk save merges into the file it names, so a
default that diverges from the file the user loaded merges into a file that does
not exist, and leaves the loaded one untouched.

## Manifest identity

`chunks.manifest_id` derives a UUID5 from the bag filename, chunk size, chunking
flag, and the source size and nanosecond mtime recorded in the manifest.

The same input therefore produces the same manifest ID across sessions, which is
what allows a reopened bag to find its chunk recovery files and its per-manifest
chunk status summaries. A different chunk size correctly produces a different
ID, since chunk 0 then covers a different range.

Processed media is not affected either way: `ViewCache` is content-addressed, so
a different manifest ID already reuses the same processed views.

`MANIFEST_NAMESPACE` in `chunks.py` is fixed for the life of the project.
Changing it makes newly generated manifests use different IDs, so new sessions
will not automatically rediscover status summaries or recovery files associated
with the old IDs. Existing manifests remain addressable by their old IDs while
their files remain present, and the content-addressed `ViewCache` is unaffected.

## Recovery interaction

Chunk autosaves are stored per scope at
`datas/annotation/chunks/<manifest_id>/<chunk_index>/<bag stem>.autosave.json`,
with the whole-recording equivalent at the root of `datas/annotation/`. They are
JSON rather than CSV because recovery must restore the editor exactly, including
axes with no blocks and shortcut keys, both of which the CSV format drops.

A successful save clears the autosave for the scope it saved, and only that
scope. During the current browser session, `MainPage` also keeps each visited
chunk's edits in memory and silently restores them when that chunk is revisited.
Before switching chunks, the latest state is flushed to the chunk-scoped
autosave. That file remains crash-recovery data: an existing autosave for a
chunk that has not been visited in the current session is applied only after
the user chooses to restore it.

## Limitations

- CSVs written from a chunked session before this change hold chunk-local times.
  They are wrong and are not repaired automatically. Test against fresh saves.
- An axis with no blocks anywhere in the recording is not represented in the
  CSV, which has one row per block. Recovery files do preserve it.
- In-memory carried edits last only for the current page session. Recovery after
  a crash, reload, or later session depends on the chunk-scoped autosave and the
  user's choice to restore it.

## Verification

From `src/backend`:

```sh
python manage.py test rosbag_processing.tests tests.test_annotation_chunking tests.test_chunks tests.test_autosave tests.test_chunk_autosave
```

`ChunkAnnotationTests` covers the clipping contract on load. Manual checks that
the automated tests do not cover:

- save in chunk 0, then chunk 2 under the same name, and confirm both sets of
  blocks are present with chunk 2's at whole-recording time
- create a block spanning a chunk boundary, save the adjacent chunk without
  editing, and confirm the file is unchanged
- save over an existing file from a chunk and confirm the prompt reports the
  count within that chunk, not the file total
- save from both the header button and "Save and Send Data" and confirm
  identical behaviour
