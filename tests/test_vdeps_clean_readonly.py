"""Regression tests: --clean must survive read-only files (Windows git objects).

On Windows, unlinking a read-only file fails with WinError 5 (unlike Linux,
where only the directory needs write permission). Git marks .git/objects
read-only, and CMake FetchContent nests such checkouts inside our build dirs
(``vdeps/<dep>/build*/_deps/<dep>-src/.git/...``), which used to crash
``--clean`` with ``PermissionError: [WinError 5] Access is denied``.

``_windows_unlink`` emulates Windows unlink semantics (writability of the
file itself is required) so these tests pin the fix on every platform, not
just on Windows CI.
"""

import errno
import os
import shutil
import stat
import sys
from contextlib import contextmanager
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def _make_readonly(path):
    """Mark a file read-only, the way git marks .git/objects."""
    os.chmod(path, stat.S_IREAD)


def _is_writable(path):
    return bool(os.stat(path).st_mode & stat.S_IWRITE)


@contextmanager
def _windows_unlink():
    """Emulate Windows: unlinking a read-only file raises PermissionError."""
    real_unlink = os.unlink

    def windows_unlink(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)):
            try:
                writable = _is_writable(path)
            except OSError:
                return real_unlink(path, *args, **kwargs)
            if not writable:
                raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_unlink(path, *args, **kwargs)

    with patch("os.unlink", side_effect=windows_unlink):
        yield


def _make_fetchcontent_tree(root):
    """Fake dep build dir with a FetchContent-style nested read-only .git."""
    pack_dir = (
        root
        / "vdeps"
        / "nvrhi"
        / "build_debug"
        / "_deps"
        / "rtxmu-src"
        / ".git"
        / "objects"
        / "pack"
    )
    pack_dir.mkdir(parents=True)
    for name in ("pack-abc123.idx", "pack-abc123.pack"):
        target = pack_dir / name
        target.write_bytes(b"git-object-data")
        _make_readonly(target)
    (root / "vdeps.toml").write_text(
        '[[dependency]]\nname = "nvrhi"\nrel_path = "nvrhi"\ncmake_options = []\n',
        encoding="utf-8",
    )
    return root / "vdeps" / "nvrhi" / "build_debug"


def test_bare_rmtree_fails_on_readonly_under_windows_semantics(tmp_path):
    """The repro, pinned: plain shutil.rmtree dies on read-only git objects."""
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "pack-abc123.idx"
    target.write_bytes(b"git-object-data")
    _make_readonly(target)

    with _windows_unlink():
        with pytest.raises(PermissionError):
            shutil.rmtree(str(tree))


@pytest.mark.parametrize("hook", [vdeps._rmtree_onerror, vdeps._rmtree_onexc])
def test_rmtree_hooks_clear_readonly_and_retry(tmp_path, hook):
    """The error hooks chmod the file writable and retry the failed call."""
    target = tmp_path / "pack-abc123.idx"
    target.write_bytes(b"git-object-data")
    _make_readonly(target)
    assert not _is_writable(target)

    calls = []

    def windows_like_unlink(path):
        if not _is_writable(path):
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        calls.append(path)
        os.unlink(path)

    hook(windows_like_unlink, str(target), None)

    assert calls == [str(target)]
    assert not target.exists()


def test_rmtree_removes_readonly_tree(tmp_path):
    """vdeps._rmtree deletes a nested read-only .git tree outright."""
    build_dir = _make_fetchcontent_tree(tmp_path)

    vdeps._rmtree(str(build_dir))

    assert not build_dir.exists()


def test_clean_removes_fetchcontent_nested_readonly_git(tmp_path):
    """End to end: --clean survives FetchContent's nested read-only .git."""
    build_dir = _make_fetchcontent_tree(tmp_path)

    with (
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("builtins.input", return_value="clean"),
        patch("sys.argv", ["vdeps.py", "--clean"]),
        _windows_unlink(),
    ):
        with pytest.raises(SystemExit) as exc:
            vdeps.main()

    assert exc.value.code == 0
    assert not build_dir.exists()
