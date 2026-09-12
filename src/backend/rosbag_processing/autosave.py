"""Crash-recovery autosave for in-progress annotations.

Autosaves live in the same folder as the exported CSVs (/app/datas/annotation/)
but use a distinct name: "<bag stem>.autosave.json". Two consequences worth
knowing:

  * list_filenames() only lists *.csv from that folder, so autosaves are never
    offered to the user as loadable annotation files.
  * save_annotation() only ever writes *.csv, so an autosave can never collide
    with a user-chosen annotation name.

Writes are atomic (temp file + os.replace) and the previous autosave is kept as
a .bak, so a crash midway through a write cannot leave an unreadable recovery
file. Unreadable files are treated as "no autosave" rather than as an error.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

AUTOSAVE_DIR = '/app/datas/annotation/'
AUTOSAVE_SUFFIX = '.autosave.json'
BACKUP_SUFFIX = '.autosave.json.bak'
SCHEMA_VERSION = 1

# Deliberately narrow: letters, digits, space, dot, underscore, hyphen.
_SAFE_STEM = re.compile(r'^[A-Za-z0-9 ._-]+$')


class AutosaveNameError(ValueError):
    """Raised when a supplied bag filename is not safe to build a path from."""


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------

def _autosave_stem(bag_filename):
    """Validate an untrusted bag filename and return its stem.

    Mirrors the check in InputInspectionSerializer. The client already filters
    names, but a client-side check is a convenience, not a security control.
    """
    if not bag_filename or not isinstance(bag_filename, str):
        raise AutosaveNameError('bag_filename is required.')

    if bag_filename != os.path.basename(bag_filename):
        raise AutosaveNameError('bag_filename must not contain a path.')

    if not bag_filename.lower().endswith('.bag'):
        raise AutosaveNameError('bag_filename must end with .bag')

    stem = bag_filename[:-4]

    if not _SAFE_STEM.match(stem):
        raise AutosaveNameError('bag_filename contains unsupported characters.')

    if not stem.strip(' .'):
        raise AutosaveNameError('bag_filename must have a usable name.')

    return stem


def _autosave_paths(bag_filename):
    """Return (autosave_path, backup_path) for a bag filename."""
    base = os.path.join(AUTOSAVE_DIR, _autosave_stem(bag_filename))
    return base + AUTOSAVE_SUFFIX, base + BACKUP_SUFFIX

# Fields that define the content of an autosave. saved_at is excluded on
# purpose: it changes on every request and is not part of the state.
_CONTENT_FIELDS = (
    'schema_version',
    'bag_filename',
    'booklist_filename',
    'annotation_filename',
    'annotation_name',
    'axes',
)


def _utc_now_iso():
    """Timezone-aware ISO 8601 fallback when the client sends no timestamp.

    The offset is included, so the browser still renders it in local time.
    """
    return datetime.now(timezone.utc).isoformat()


def _read_primary(bag_filename):
    """Read only the primary autosave, ignoring the .bak.

    Used for the unchanged-content check. read_autosave() falls back to the
    backup, which would be wrong here: if the primary is corrupt and the backup
    happens to match the incoming state, we must still write a good primary.
    """
    path, _ = _autosave_paths(bag_filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except (ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _same_content(existing, payload):
    """True when the stored autosave holds the same state as the new one."""
    return all(
        existing.get(field) == payload.get(field) for field in _CONTENT_FIELDS
    )


    
# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def write_autosave(bag_filename, payload):
    """Atomically write an autosave payload, rotating the previous one to .bak."""
    path, backup_path = _autosave_paths(bag_filename)
    os.makedirs(AUTOSAVE_DIR, exist_ok=True)

    if os.path.isfile(path):
        try:
            os.replace(path, backup_path)
        except OSError:
            # A missing backup is not worth failing the autosave over.
            pass

    handle_fd, tmp_path = tempfile.mkstemp(
        dir=AUTOSAVE_DIR, prefix='.autosave-', suffix='.tmp'
    )
    try:
        with os.fdopen(handle_fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return path


def read_autosave(bag_filename):
    """Return the autosave payload, or None if there is nothing usable.

    Falls back to the .bak copy if the primary file is missing or corrupt. The
    returned payload carries 'recovered_from_backup' so the interface can be
    honest about which copy the user is being offered.
    """
    path, backup_path = _autosave_paths(bag_filename)

    for candidate, from_backup in ((path, False), (backup_path, True)):
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except (ValueError, OSError):
            continue

        if not isinstance(payload, dict):
            continue
        if payload.get('schema_version') != SCHEMA_VERSION:
            continue
        if not isinstance(payload.get('axes'), list):
            continue

        payload['recovered_from_backup'] = from_backup
        return payload

    return None


def delete_autosave(bag_filename):
    """Remove the autosave and its backup. Returns True if anything was removed."""
    removed = False
    for candidate in _autosave_paths(bag_filename):
        try:
            os.remove(candidate)
            removed = True
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return removed


def _summarise(payload):
    """Metadata only: enough to render the restore prompt, without the axes."""
    axes = payload.get('axes', [])
    return {
        'exists': True,
        'bag_filename': payload.get('bag_filename', ''),
        'booklist_filename': payload.get('booklist_filename', ''),
        'annotation_filename': payload.get('annotation_filename', ''),
        'annotation_name': payload.get('annotation_name', ''),
        'saved_at': payload.get('saved_at', ''),
        'axis_count': len(axes),
        'block_count': sum(len(axis.get('blocks', []) or []) for axis in axes),
        'recovered_from_backup': payload.get('recovered_from_backup', False),
    }


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@csrf_exempt
@api_view(['POST'])
def save_autosave(request):
    """Write the current in-progress annotation state for a bag."""
    bag_filename = request.data.get('bag_filename')
    axes = request.data.get('axes')

    try:
        _autosave_stem(bag_filename)
    except AutosaveNameError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(axes, list):
        return Response(
            {'error': 'axes must be a list.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = {
        'schema_version': SCHEMA_VERSION,
        'bag_filename': bag_filename,
        'booklist_filename': request.data.get('booklist_filename') or '',
        'annotation_filename': request.data.get('annotation_filename') or '',
        'annotation_name': request.data.get('annotation_name') or '',
        'saved_at': request.data.get('saved_at') or _utc_now_iso(),
        'axes': axes,
    }

    # Idempotency: identical state is not rewritten. This keeps saved_at
    # honest about when the work actually dates from, and protects the .bak
    # from being overwritten with a duplicate of the current file.
    existing = _read_primary(bag_filename)
    if existing is not None and _same_content(existing, payload):
        return Response({
            'saved': False,
            'unchanged': True,
            'saved_at': existing.get('saved_at', ''),
            'axis_count': len(axes),
        })

    try:
        write_autosave(bag_filename, payload)
    except OSError as exc:
        return Response(
            {'error': f'Unable to write autosave: {str(exc)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'saved': True,
        'unchanged': False,
        'saved_at': payload['saved_at'],
        'axis_count': len(axes),
    })


@api_view(['GET'])
def check_autosave(request):
    """Report whether an autosave exists for a bag, returning metadata only."""
    bag_filename = request.query_params.get('bag_filename')

    try:
        _autosave_stem(bag_filename)
    except AutosaveNameError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    payload = read_autosave(bag_filename)
    if payload is None:
        return Response({'exists': False})

    return Response(_summarise(payload))


@api_view(['GET'])
def load_autosave(request):
    """Return the full autosave payload, including the axes."""
    bag_filename = request.query_params.get('bag_filename')

    try:
        _autosave_stem(bag_filename)
    except AutosaveNameError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    payload = read_autosave(bag_filename)
    if payload is None:
        return Response(
            {'error': 'No autosave found for this ROSBag.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(payload)


@csrf_exempt
@api_view(['DELETE'])
def discard_autosave(request):
    """Remove the autosave for a bag, after a real save or an explicit discard."""
    bag_filename = request.query_params.get('bag_filename')

    try:
        _autosave_stem(bag_filename)
    except AutosaveNameError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'deleted': delete_autosave(bag_filename)})
