"""Optional annotation/codebook attachments, shared by both HTTP paths."""
import json
from pathlib import Path


def annotations_for_chunk(annotation_data, chunk):
    start, end = chunk['start_seconds'], chunk['end_seconds']
    return [{**axis, 'annotationBlocks': [
        {**block, 'start': max(block['start'], start) - start,
         'end': min(block['end'], end) - start}
        for block in axis.get('annotationBlocks', [])
        if block['end'] > start and block['start'] < end
    ]} for axis in annotation_data or []]


def attach_metadata(result, booklist_filename=None, annotation_filename=None, chunk=None):
    from .data_utils import load_annotation
    result = {**result, 'booklist_data': {}, 'annotation_data': None}
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
            result['annotation_data'] = annotations_for_chunk(annotations, chunk) if chunk else annotations
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
