"""Small cross-platform file locks for coordinating Flow processes."""

import hashlib
import os
import tempfile


def path(name, namespace):
    digest = hashlib.sha256(os.path.abspath(namespace).encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"flow-{name}-{digest}.lock")


class ProcessFileLock:
    def __init__(self, lock_path):
        self.path = lock_path
        self._file = None

    @property
    def owned(self):
        return self._file is not None

    def acquire(self):
        if self._file is not None:
            return True
        lock_file = None
        try:
            lock_file = open(self.path, "a+b")
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            if lock_file is not None:
                lock_file.close()
            return False
        self._file = lock_file
        return True

    def release(self):
        lock_file = self._file
        if lock_file is None:
            return
        try:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError):
            pass
        lock_file.close()
        self._file = None

    def held_elsewhere(self):
        if self._file is not None:
            return False
        probe = ProcessFileLock(self.path)
        if probe.acquire():
            probe.release()
            return False
        return True
