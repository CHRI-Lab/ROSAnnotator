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
backend immediately rewrites every boundary-crossing block into independent
blocks aligned to the confirmed chunk boundaries, before the first chunk is
processed.

For example, a 50–70 s block with 60-second chunks becomes two CSV rows:
50–60 s and 60–70 s.

The normal loader still displays every block that **overlaps** its range,
clipped to it.

`view_metadata.clip_to_chunk` defines this, and `annotations_for_chunk` is
implemented in terms of it so the two cannot diverge.

Clipping creates a problem on the way back. Writing the clipped block to the
file naively either duplicates the original or discards the part outside the
chunk. The merge resolves it by identity rather than position:

- an incoming block still matching an existing block's clipped form is
  **unedited**, and the original absolute block is restored
- anything else is new or edited, and is written at chunk offset plus its
  chunk-local time
- an existing block the chunk displayed but the request no longer contains was
  **deleted by the user**, and does not return

A load and save with no edits is therefore exact.

## Merge

`views.merge_chunk_annotations(existing, incoming, chunk)`:

1. Carry through every existing block the chunk did not display.
2. Re-add the chunk's current blocks, restoring originals where unedited.
3. Sort each axis by start time and renumber axis IDs from 1.

Axes are matched on `(axisName, axisType)`. Numeric IDs are reassigned by the
editor on every load and are not stable across sessions or chunks, so they
cannot be used for identity. IDs are renumbered on write because
`data_utils.load_annotation` groups rows by ID, and a collision would merge two
distinct axes into one.

The CSV is written through a temporary file and `os.replace`. The merge reads
the file before writing it, so a failure part-way through must not truncate a
set that was complete a moment earlier.

## Save request

`POST /api/save_annotation/`

| Field | Meaning |
| --- | --- |
| `annotation_name` | Filename stem; `.csv` is appended by the view |
| `annotation_data` | Axes and blocks, in the editor's current reference frame |
| `confirm_overwrite` | Proceed despite a reported conflict |
| `manifest_id` | Chunk scope; required with `chunk_index` |
| `chunk_index` | Chunk scope; required with `manifest_id` |

Chunk bounds are read from the manifest rather than sent by the client, so a
save cannot disagree with the range the loader used.

Responses:

| Status | Meaning |
| --- | --- |
| 200 | Written |
| 400 | Validation failed; body carries per-field messages |
| 404 | Named manifest or chunk does not exist |
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
Changing it orphans every existing cache entry and recovery file.

This supersedes the note in the data-view contracts that manifest generation
remains UUID4.

## Recovery interaction

Chunk autosaves are stored per scope at
`datas/annotation/chunks/<manifest_id>/<chunk_index>/<bag stem>.autosave.json`,
with the whole-recording equivalent at the root of `datas/annotation/`. They are
JSON rather than CSV because recovery must restore the editor exactly, including
axes with no blocks and shortcut keys, both of which the CSV format drops.

A successful save clears the autosave for the scope it saved, and only that
scope. A chunk save merges one chunk's range, so other chunks' unexported work
exists nowhere but their own recovery files.

## Limitations

- CSVs written from a chunked session before this change hold chunk-local times.
  They are wrong and are not repaired automatically. Test against fresh saves.
- An axis with no blocks anywhere in the recording is not represented in the
  CSV, which has one row per block. Recovery files do preserve it.
- Legacy or otherwise unconfirmed annotation data can still contain a
  boundary-spanning block. Confirming a chunked session with an imported file
  permanently splits those blocks before they can be edited.
- Switching chunks currently relies on autosave to preserve the rest of the
  annotation, so autosave is serving both as an in-session state carrier and as
  crash recovery. These should be separated.

## Verification

From `src/backend`:

```sh
python manage.py test rosbag_processing.tests tests.test_annotation_chunking tests.test_chunks tests.test_autosave tests.test_chunk_autosave
```

`ChunkAnnotationTests` covers the clipping contract on load, and
`test_annotation_chunking` covers permanent boundary splitting. Use this manual
acceptance scenario as well:

1. Load the recording without chunking, create one block from 50–70 s, and save
   it as an annotation file.
2. Reload that annotation file with 60-second chunks.
3. Delete 50–60 s in chunk 1, use "Save and Send Data", then load the annotation
   without chunking. The 60–70 s block must still exist.
4. Repeat from the original file, edit 50–60 s in chunk 1, and save/send. A full
   load must show two separate blocks with different content.
5. Repeat the edit, then navigate directly to chunk 2. Its local 0–10 s block
   (whole-recording 60–70 s) must still exist unchanged.

These checks use the existing autosave flow as-is; permanent splitting does not
change autosave behavior.
