"""Optional annotation/codebook attachments, shared by both HTTP paths."""
import json
import math
from pathlib import Path

# A bag duration reaches us from three places: the reader, the manifest, and
# the encoded video. They agree to well under half a second, and a different
# recording of the same length to within half a second is not a case worth
# chasing.
DURATION_TOLERANCE_SECONDS = 0.5

# A block drawn to the visual end of the timeline lands slightly past a
# duration that is not a round number, so this has to clear ordinary
# edge-of-recording editing rather than just floating-point noise. Measured
# against real data: a block ending at 317.8 in a 317.2 second recording is
# normal editing, not a different recording.
OVERFLOW_TOLERANCE_SECONDS = 1.0


def annotation_end_seconds(annotations):
    """The largest end time in the file, in whole-recording seconds."""
    ends = [
        block['end']
        for axis in annotations or []
        for block in axis.get('annotationBlocks', [])
    ]
    return max(ends) if ends else 0.0


def check_annotation_source(annotations, recorded, bag_filename, source_duration):
    """Compare what an annotation file records against what is being loaded.

    recorded is read_annotation_metadata's output: either key may be absent,
    which means the file predates this column and its provenance is unknown.
    Unknown is not a mismatch. Every annotation file written before this
    feature has no record at all, so treating absence as a mismatch would
    prompt on the entire existing corpus.

    annotations must be the unclipped file contents. In a chunked session the
    displayed blocks are clipped to the chunk, so measuring those would report
    no overflow however far the file actually runs past the recording.
    """
    recorded_name = recorded.get('bag_filename')
    recorded_duration = recorded.get('source_duration')

    name_differs = (
        recorded_name is not None
        and bag_filename is not None
        # Compared case-insensitively: the datas directory is bind-mounted from
        # Windows in normal use, where two names differing only in case are the
        # same file.
        and recorded_name.casefold() != bag_filename.casefold()
    )

    duration_differs = (
        recorded_duration is not None
        and source_duration is not None
        and not math.isclose(
            recorded_duration, source_duration,
            rel_tol=0.0, abs_tol=DURATION_TOLERANCE_SECONDS,
        )
    )

    if recorded_name is None and recorded_duration is None:
        status = 'unknown'
    elif name_differs or duration_differs:
        status = 'mismatch'
    else:
        status = 'ok'

    end = annotation_end_seconds(annotations)

    # Two different situations needing different handling, so they are counted
    # separately and never both. A block straddling the end has a real referent
    # in this recording and can be trimmed to it. A block starting after the
    # end has nothing to point at and can only be discarded.
    straddling = 0
    orphaned = 0
    if source_duration is not None:
        for axis in annotations or []:
            for block in axis.get('annotationBlocks', []):
                if block['start'] >= source_duration:
                    orphaned += 1
                elif block['end'] > source_duration + OVERFLOW_TOLERANCE_SECONDS:
                    straddling += 1

    return {
        'status': status,
        'name_differs': name_differs,
        'duration_differs': duration_differs,
        'recorded_bag_filename': recorded_name,
        'recorded_duration': recorded_duration,
        'loaded_bag_filename': bag_filename,
        'loaded_duration': source_duration,
        'annotation_end_seconds': end,
        'overflows': bool(straddling or orphaned),
        'overflow_block_count': straddling,
        'orphan_block_count': orphaned,
    }


def clip_to_chunk(block, chunk):
    """The chunk-local form annotations_for_chunk would produce, or None.

    The merge compares against this, so the two can never disagree about what
    a chunk displays.
    """
    start, end = chunk['start_seconds'], chunk['end_seconds']
    if not (block['end'] > start and block['start'] < end):
        return None
    return (max(block['start'], start) - start, min(block['end'], end) - start)

def clip_to_recording(annotation_data, source_duration):
    """Drop or trim blocks falling outside the recording.

    A block starting past the end has no referent here and goes. A block
    straddling the end is trimmed to it, but only once it runs more than
    OVERFLOW_TOLERANCE_SECONDS over, so ordinary editing at the end of a
    timeline is left exactly as it is.

    Used on both the load response and the existing file during a chunk merge,
    so the two cannot disagree about what survives.
    """
    if source_duration is None:
        return annotation_data
    limit = source_duration + OVERFLOW_TOLERANCE_SECONDS
    result = []
    for axis in annotation_data or []:
        blocks = []
        for block in axis.get('annotationBlocks', []):
            if block['start'] >= source_duration:
                continue
            blocks.append(
                {**block, 'end': source_duration}
                if block['end'] > limit else block
            )
        result.append({**axis, 'annotationBlocks': blocks})
    return result

def annotations_for_chunk(annotation_data, chunk):
    result = []
    for axis in annotation_data or []:
        blocks = []
        for block in axis.get('annotationBlocks', []):
            clipped = clip_to_chunk(block, chunk)
            if clipped is not None:
                blocks.append({**block, 'start': clipped[0], 'end': clipped[1]})
        result.append({**axis, 'annotationBlocks': blocks})
    return result


def attach_metadata(result, booklist_filename=None, annotation_filename=None,
                    chunk=None, bag_filename=None, source_duration=None):
    from .data_utils import load_annotation, read_annotation_metadata
    result = {**result, 'booklist_data': {}, 'annotation_data': None,
              'annotation_source_check': None}
    warnings = []
    if booklist_filename:
        try:
            with (Path('/app/datas/booklist') / booklist_filename).open(encoding='utf-8') as stream:
                result['booklist_data'] = json.load(stream)
        except (OSError, ValueError) as exc:
            warnings.append(f'Unable to read booklist: {exc}')
    if annotation_filename:
        try:
            annotations = load_annotation(annotation_filename)
            # Checked against the unclipped file, before the chunk view of it.
            try:
                recorded = read_annotation_metadata(annotation_filename)
            except (OSError, ValueError):
                recorded = {}
            check = check_annotation_source(
                annotations, recorded, bag_filename, source_duration,
            )
            result['annotation_source_check'] = check
            if chunk:
                result['annotation_data'] = annotations_for_chunk(annotations, chunk)
            else:
                result['annotation_data'] = clip_to_recording(
                    annotations, source_duration,
                )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            warnings.append(f'Unable to read annotation: {exc}')

    for name in ('annotations', 'statistics-annotations', 'statistics-tiers'):
        view = result.get('views', {}).get(name)
        if view and view['available']:
            result['views'][name] = {**view, 'warnings': [*view['warnings'], *warnings],
                                    'processed_data': {**view['processed_data'],
                                                       'annotation_data': result['annotation_data']}}
    result['warnings'] = warnings
    return result
