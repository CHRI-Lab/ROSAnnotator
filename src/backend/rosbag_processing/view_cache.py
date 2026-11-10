"""Content-addressed per-view caching, separate from processors and manifests."""
import hashlib
import json
import os
import tempfile
import errno
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


UUID_EPOCH_OFFSET_100NS = 0x01B21DD213814000


def uuid6_cache_key(identity, source_mtime_ns):
    """Return a deterministic UUIDv6 key without sacrificing cache reuse."""
    serialized = json.dumps(
        identity, sort_keys=True, allow_nan=False, separators=(',', ':'),
    ).encode()
    timestamp = (source_mtime_ns // 100 + UUID_EPOCH_OFFSET_100NS) & ((1 << 60) - 1)
    entropy = int.from_bytes(
        hashlib.blake2b(serialized, digest_size=8, person=b'ros-view-cache').digest(),
        'big',
    ) & ((1 << 62) - 1)
    value = (
        (timestamp >> 28) << 96
        | ((timestamp >> 12) & 0xffff) << 80
        | 0x6 << 76
        | (timestamp & 0xfff) << 64
        | 0b10 << 62
        | entropy
    )
    return uuid.UUID(int=value)


def atomic_json(destination, payload):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=destination.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, allow_nan=False)
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ViewCache:
    def __init__(self, root, bag_path, chunk=None):
        self.root = Path(root) / 'views'
        source = Path(bag_path).resolve()
        stat = source.stat()
        self.source = [str(source), stat.st_size, stat.st_mtime_ns]
        self.chunk = chunk

    def identity(self, processor, topics, options, dependencies):
        return {'source': self.source, 'view': processor.view_id,
                'version': processor.cache_version, 'topics': topics, 'options': options,
                'bounds': [self.chunk['start_seconds'], self.chunk['end_seconds']] if self.chunk else None,
                'dependencies': dependencies}

    def identifier(self, identity):
        """Internal data-view ID."""
        return uuid6_cache_key(identity, self.source[2])

    def directory(self, processor, topics, options, dependencies):
        identity = self.identity(processor, topics, options, dependencies)
        return self.root / str(self.identifier(identity))

    def legacy_directory(self, processor, topics, options, dependencies):
        """Previous SHA-256 location, used only to read existing cache entries."""
        identity = self.identity(processor, topics, options, dependencies)
        key = hashlib.sha256(
            json.dumps(identity, sort_keys=True, allow_nan=False).encode(),
        ).hexdigest()
        return self.root / key

    @staticmethod
    def load(directory):
        try:
            result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
            if (not isinstance(result, dict) or result.get('status') != 'ready'
                    or result.get('available') is not True
                    or not isinstance(result.get('processed_data'), dict)):
                return None
            for artifact in result.get('processed_data', {}).get('artifacts', []):
                if not Path(artifact).is_file():
                    return None
            return result
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    @contextmanager
    def lock(directory):
        """OS advisory lock releases automatically even when a worker crashes."""
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / '.lock').open('a+b') as stream:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                while True:
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        time.sleep(0.05)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)
