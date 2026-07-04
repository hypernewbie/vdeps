"""Tests for the ``--parallel N`` cap.

This flag threads a single integer into CMake's ``--parallel`` invocation.
It does NOT affect platform_subdir, build-dir prefix, the toolchain
fingerprint, or auto-skip -- the produced binaries are identical, only the
build speed/cap differs.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def run_main(root, argv):
    with (
        patch("sys.argv", ["vdeps.py", *argv]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
    ):
        vdeps.main()


# --- argparse type ---


def test_validate_parallel_accepts_one():
    assert vdeps._validate_parallel("1") == 1


def test_validate_parallel_accepts_high_numbers():
    """No hard ceiling; user can pin to a specific core count."""
    assert vdeps._validate_parallel("128") == 128


def test_validate_parallel_rejects_zero():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vdeps._validate_parallel("0")


def test_validate_parallel_rejects_negative():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vdeps._validate_parallel("-1")


def test_validate_parallel_rejects_non_integer():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vdeps._validate_parallel("lots")


# --- build_cmd composition ---


def _capture_build_cmd(argv):
    """Run vdeps.main with the given argv and capture the cmake --build command."""
    captured = []

    real_run = vdeps.run_command

    def fake_run(cmd, cwd=None, env=None):
        # First command is cmake -S configure; second is cmake --build.
        if cmd and cmd[0] == "cmake" and "--build" in cmd:
            captured.append(list(cmd))

    return captured, fake_run


def test_parallel_default_omits_count(tmp_path):
    """Bare --parallel (no value) is identical to today's behavior."""
    toml_path = tmp_path / "vdeps.toml"
    toml_path.write_text(
        '[[dependency]]\nname = "x"\nrel_path = "x"\ncmake_options = []\n'
    )
    (tmp_path / "vdeps" / "x").mkdir(parents=True)

    captured, fake_run = _capture_build_cmd([])

    with (
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.IS_MACOS", False),
        patch("glob.glob", return_value=[]),
        patch("vdeps.run_command", side_effect=fake_run),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
    ):
        run_main(tmp_path, ["x"])

    assert captured, "expected at least one cmake --build invocation"
    build_cmd = captured[0]
    # --parallel present, no integer follows it directly.
    parallel_idx = build_cmd.index("--parallel")
    assert parallel_idx == len(build_cmd) - 1 or not build_cmd[parallel_idx + 1].isdigit()


def test_parallel_four_appends_count(tmp_path):
    toml_path = tmp_path / "vdeps.toml"
    toml_path.write_text(
        '[[dependency]]\nname = "x"\nrel_path = "x"\ncmake_options = []\n'
    )
    (tmp_path / "vdeps" / "x").mkdir(parents=True)

    captured, fake_run = _capture_build_cmd(["--parallel", "4"])

    with (
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.IS_MACOS", False),
        patch("glob.glob", return_value=[]),
        patch("vdeps.run_command", side_effect=fake_run),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
    ):
        run_main(tmp_path, ["x", "--parallel", "4"])

    assert captured
    cmd = captured[0]
    # --parallel 4 contiguously
    pi = cmd.index("--parallel")
    assert cmd[pi + 1] == "4"


def test_parallel_one_serial(tmp_path):
    toml_path = tmp_path / "vdeps.toml"
    toml_path.write_text(
        '[[dependency]]\nname = "x"\nrel_path = "x"\ncmake_options = []\n'
    )
    (tmp_path / "vdeps" / "x").mkdir(parents=True)

    captured, fake_run = _capture_build_cmd([])

    with (
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.IS_MACOS", False),
        patch("glob.glob", return_value=[]),
        patch("vdeps.run_command", side_effect=fake_run),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
    ):
        run_main(tmp_path, ["x", "--parallel", "1"])

    assert captured[0][captured[0].index("--parallel") + 1] == "1"


def test_parallel_composes_with_sanitize(tmp_path):
    """--sanitize thread --parallel 2 still emits both -fsanitize= and --parallel 2."""
    toml_path = tmp_path / "vdeps.toml"
    toml_path.write_text(
        '[[dependency]]\nname = "x"\nrel_path = "x"\ncmake_options = []\n'
    )
    (tmp_path / "vdeps" / "x").mkdir(parents=True)

    captured_cmake = []

    real_capture = []

    def fake_run(cmd, cwd=None, env=None):
        real_capture.append(list(cmd))

    with (
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.IS_MACOS", False),
        patch("glob.glob", return_value=[]),
        patch("vdeps.run_command", side_effect=fake_run),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
    ):
        run_main(tmp_path, ["x", "--sanitize", "thread", "--parallel", "2"])

    # Two commands per config: configure + build. Look at any that include
    # -fsanitize= in args and verify --parallel 2 sits on a build command.
    saw_sanitize_in_args = False
    saw_parallel_two = False
    for cmd in real_capture:
        joined = " ".join(cmd)
        if "-fsanitize=thread" in joined:
            saw_sanitize_in_args = True
        if "--build" in cmd:
            pi = cmd.index("--parallel")
            if cmd[pi + 1] == "2":
                saw_parallel_two = True
    assert saw_sanitize_in_args
    assert saw_parallel_two


# --- fingerprint should NOT include parallel ---


def test_fingerprint_does_not_include_parallel():
    """Parallel is a perf knob, not a toolchain identity; it must not invalidate auto-skip."""
    a = vdeps.get_toolchain_fingerprint(False, False, None)
    b = vdeps.get_toolchain_fingerprint(False, False, None)
    # No parallel key in the fingerprint either way.
    assert "parallel" not in a
    assert "parallel" not in b
    # Same fingerprint regardless of what parallel value the user might set.
    assert a == b


def test_fingerprint_unchanged_with_sanitize_off():
    """sanitize=None fingerprint is identical across two parallel calls."""
    a = vdeps.get_toolchain_fingerprint(False, False, None)
    b = vdeps.get_toolchain_fingerprint(False, False, None)
    assert a == b
    assert a["sanitize"] is None


# --- CLI rejects ---


def test_cli_rejects_parallel_zero(tmp_path, capsys):
    (tmp_path / "vdeps.toml").write_text(
        '[[dependency]]\nname = "x"\nrel_path = "x"\ncmake_options = []\n'
    )
    with pytest.raises(SystemExit) as exc:
        run_main(tmp_path, ["x", "--parallel", "0"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "must be >= 1" in captured.err or "invalid" in captured.err
