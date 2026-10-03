import importlib
from pathlib import Path
from unittest import mock

import pytest

from utils.file_lock import interprocess_file_lock


class WindowsAdapter:
    LK_NBLCK = 1
    LK_UNLCK = 2

    def __init__(self):
        self.calls = []

    def locking(self, descriptor, operation, length):
        self.calls.append((descriptor, operation, length))


def test_normal_acquisition_release_and_repeated_acquisition(tmp_path):
    path = tmp_path / "migration.lock"
    with interprocess_file_lock(path):
        assert path.read_bytes() in {b"", b"\0"}
    with interprocess_file_lock(path):
        assert path.is_file()


def test_exception_still_releases_lock(tmp_path):
    path = tmp_path / "migration.lock"
    with pytest.raises(RuntimeError, match="boom"):
        with interprocess_file_lock(path):
            raise RuntimeError("boom")
    # A leaked lock would make this acquisition time out.
    with interprocess_file_lock(path, timeout=0.2):
        pass


def test_posix_adapter_uses_exclusive_nonblocking_flock(tmp_path):
    adapter = mock.Mock(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8)
    with interprocess_file_lock(tmp_path / "posix.lock", platform="posix", adapter=adapter):
        pass
    assert adapter.flock.call_args_list[0].args[1] == 6
    assert adapter.flock.call_args_list[1].args[1] == 8


def test_windows_adapter_locks_one_existing_byte_and_unlocks(tmp_path):
    adapter = WindowsAdapter()
    path = tmp_path / "windows.lock"
    with interprocess_file_lock(path, platform="nt", adapter=adapter):
        assert path.stat().st_size == 1
    assert [call[1:] for call in adapter.calls] == [(adapter.LK_NBLCK, 1), (adapter.LK_UNLCK, 1)]


def test_windows_path_never_imports_fcntl(tmp_path):
    adapter = WindowsAdapter()
    real_import = importlib.import_module

    def guarded_import(name, *args, **kwargs):
        if name == "fcntl":
            raise AssertionError("Windows path attempted to import fcntl")
        return real_import(name, *args, **kwargs)

    with mock.patch("utils.file_lock.importlib.import_module", side_effect=guarded_import):
        with interprocess_file_lock(tmp_path / "windows.lock", platform="nt", adapter=adapter):
            pass


def test_factory_configuration_has_no_unconditional_fcntl_import():
    source = Path("utils/factory_configuration.py").read_text(encoding="utf-8")
    assert "import fcntl" not in source
    import utils.factory_configuration
