"""Content-addressed per-view caching, separate from processors and manifests."""
import hashlib
import json
import os
import tempfile
import errno
import time
from contextlib import contextmanager
from pathlib import Path


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

    def directory(self, processor, topics, options, dependencies):
        identity = {'source': self.source, 'view': processor.view_id,
                    'version': processor.cache_version, 'topics': topics, 'options': options,
                    'bounds': [self.chunk['start_seconds'], self.chunk['end_seconds']] if self.chunk else None,
                    'dependencies': dependencies}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
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
