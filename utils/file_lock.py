"""Small cross-platform inter-process file-lock abstraction.

The platform modules are imported lazily so importing application modules on
Windows never attempts to import POSIX-only :mod:`fcntl` (and vice versa).
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import importlib
import os
from pathlib import Path
import time
from typing import Iterator


class FileLockTimeout(TimeoutError):
    """Raised when an inter-process lock cannot be acquired in time."""


def _retryable(exc: OSError) -> bool:
    return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}


def _acquire_windows(handle, adapter, deadline: float, poll_interval: float) -> None:
    while True:
        try:
            handle.seek(0)
            adapter.locking(handle.fileno(), adapter.LK_NBLCK, 1)
            return
        except OSError as exc:
            if not _retryable(exc) or time.monotonic() >= deadline:
                raise FileLockTimeout("timed out acquiring Windows file lock") from exc
            time.sleep(poll_interval)


def _release_windows(handle, adapter) -> None:
    handle.seek(0)
    adapter.locking(handle.fileno(), adapter.LK_UNLCK, 1)


def _acquire_posix(handle, adapter, deadline: float, poll_interval: float) -> None:
    while True:
        try:
            adapter.flock(handle.fileno(), adapter.LOCK_EX | adapter.LOCK_NB)
            return
        except OSError as exc:
            if not _retryable(exc) or time.monotonic() >= deadline:
                raise FileLockTimeout("timed out acquiring POSIX file lock") from exc
            time.sleep(poll_interval)


def _release_posix(handle, adapter) -> None:
    adapter.flock(handle.fileno(), adapter.LOCK_UN)


@contextmanager
def interprocess_file_lock(lock_path: Path, *, timeout: float = 30.0,
                           poll_interval: float = 0.05, platform: str | None = None,
                           adapter=None) -> Iterator[None]:
    """Exclusively lock one byte of a dedicated lock file across processes.

    ``platform`` and ``adapter`` are test seams for exercising both adapters on
    one CI host; production callers should not pass either argument.
    """
    if timeout < 0 or poll_interval <= 0:
        raise ValueError("lock timeout and poll interval must be positive")
    selected = platform or os.name
    if selected not in {"nt", "posix"}:
        raise RuntimeError(f"unsupported locking platform: {selected}")
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    # a+b is non-truncating, read/write, and exposes a descriptor suitable for
    # both flock and Windows byte-range locking.
    with lock_path.open("a+b") as handle:
        if selected == "nt":
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            implementation = adapter or importlib.import_module("msvcrt")
            acquire, release = _acquire_windows, _release_windows
        else:
            implementation = adapter or importlib.import_module("fcntl")
            acquire, release = _acquire_posix, _release_posix
        acquired = False
        try:
            acquire(handle, implementation, deadline, poll_interval)
            acquired = True
            yield
        finally:
            if acquired:
                release(handle, implementation)
