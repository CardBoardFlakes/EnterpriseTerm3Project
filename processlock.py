"""Small cross-platform file locks for coordinating Flow processes."""

import hashlib
import glob
import os
import tempfile


def _namespace_digest(namespace):
    return hashlib.sha256(os.path.abspath(namespace).encode()).hexdigest()[:16]


def path(name, namespace):
    digest = _namespace_digest(namespace)
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


class ProcessPresence:
    """Track whether one or more processes of a named kind are alive."""

    def __init__(self, name, namespace, pid=None):
        self.name = name
        self.namespace = namespace
        self.pid = os.getpid() if pid is None else pid
        self._lock = ProcessFileLock(
            path(f"{self.name}-{self.pid}", self.namespace))

    def register(self):
        return self._lock.acquire()

    def unregister(self):
        own_path = self._lock.path
        self._lock.release()
        try:
            os.remove(own_path)
        except OSError:
            pass

    def active(self):
        if self._lock.owned:
            return True
        digest = _namespace_digest(self.namespace)
        pattern = os.path.join(
            tempfile.gettempdir(), f"flow-{self.name}-*-{digest}.lock")
        return any(
            ProcessFileLock(candidate).held_elsewhere()
            for candidate in glob.glob(pattern))
