"""UX tests: quiet-by-default output, --verbose full deets, solarized [TAG] UI."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def write_config(root, body):
    (root / "vdeps.toml").write_text(body.strip() + "\n", encoding="utf-8")


def run_main(root, argv):
    with (
        patch("sys.argv", ["vdeps.py", *argv]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
    ):
        vdeps.main()


def completed(returncode=0, stdout="", stderr=""):
    return type(
        "CompletedResult",
        (),
        {"returncode": returncode, "stdout": stdout, "stderr": stderr},
    )()


def make_dep_with_artifact(root, name="demo", lib="demo"):
    write_config(
        root,
        f"""
        [[dependency]]
        name = "{name}"
        rel_path = "{name}"
        cmake_options = []
        libs = ["{lib}"]
        """,
    )
    dep_dir = root / "vdeps" / name
    dep_dir.mkdir(parents=True, exist_ok=True)
    for config in ("debug", "release"):
        build_dir = dep_dir / f"build_{config}"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / f"{lib}{vdeps.LIB_EXT}").write_text("lib", encoding="utf-8")
        # A CMakeCache makes --build consider the dir valid; harmless otherwise.
        (build_dir / "CMakeCache.txt").write_text("x", encoding="utf-8")


@pytest.fixture
def reset_ui_globals():
    old_color = vdeps._UI_COLOR_OVERRIDE
    old_verbose = vdeps._UI_VERBOSE
    yield
    vdeps._UI_COLOR_OVERRIDE = old_color
    vdeps._UI_VERBOSE = old_verbose


def test_quiet_hides_cmake_command_and_captures(tmp_path, capsys, reset_ui_globals):
    """Default run: no 'Running:' spam, subprocess output captured."""
    make_dep_with_artifact(tmp_path)
    calls = []

    def fake_subprocess(command, cwd=None, env=None, shell=False, **kwargs):
        calls.append(kwargs)
        return completed(0)

    with patch("subprocess.run", side_effect=fake_subprocess):
        run_main(tmp_path, ["demo"])

    out = capsys.readouterr().out
    assert "Running:" not in out
    assert calls, "expected cmake invocations"
    assert all(k.get("capture_output") is True for k in calls)


def test_verbose_shows_command_and_per_file(tmp_path, capsys, reset_ui_globals):
    """--verbose: full command echo + per-file copy details."""
    make_dep_with_artifact(tmp_path)

    def fake_subprocess(command, cwd=None, env=None, shell=False, **kwargs):
        return completed(0)

    with patch("subprocess.run", side_effect=fake_subprocess):
        run_main(tmp_path, ["--verbose", "demo"])

    out = capsys.readouterr().out
    assert "Running:" in out
    assert "Copying lib" in out
    assert vdeps._UI_VERBOSE is True


def test_quiet_shows_summary_not_per_file(tmp_path, capsys, reset_ui_globals):
    """Default run: one [COPY] summary per config instead of per-file lines."""
    make_dep_with_artifact(tmp_path)

    with patch("subprocess.run", side_effect=lambda *a, **k: completed(0)):
        run_main(tmp_path, ["demo"])

    out = capsys.readouterr().out
    assert "Copying lib" not in out
    assert "[COPY]" in out
    assert "copied" in out


def test_run_command_failure_shows_tail_and_hint(capsys, reset_ui_globals):
    """Quiet failure prints the error, captured tail, and --verbose hint."""
    vdeps._UI_VERBOSE = False
    with patch(
        "subprocess.run",
        return_value=completed(1, stdout="out-line\n", stderr="err-boom\n"),
    ):
        with pytest.raises(SystemExit) as exc:
            vdeps.run_command(["cmake", "--build", "x"])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Error: Command failed" in out
    assert "err-boom" in out
    assert "--verbose" in out


def test_run_command_verbose_streams_live(capsys, reset_ui_globals):
    """verbose=True echoes the command and does not capture output."""
    seen = {}

    def fake_subprocess(command, cwd=None, env=None, shell=False, **kwargs):
        seen.update(kwargs)
        return completed(0)

    with patch("subprocess.run", side_effect=fake_subprocess):
        vdeps.run_command(["cmake", "--version"], verbose=True)

    out = capsys.readouterr().out
    assert "Running:" in out
    assert seen.get("capture_output") is not True


def test_progress_counter_and_tags(tmp_path, capsys, reset_ui_globals):
    """Ninja-style [1/2]/[2/2] progress plus semantic [TAG]s."""
    make_dep_with_artifact(tmp_path)

    with patch("subprocess.run", side_effect=lambda *a, **k: completed(0)):
        run_main(tmp_path, ["demo"])

    out = capsys.readouterr().out
    assert "[1/2]" in out
    assert "[2/2]" in out
    for tag in ("[INFO]", "[DEP]", "[COPY]", "[SUCCESS]"):
        assert tag in out


def test_no_color_flag_disables_ansi(tmp_path, capsys, reset_ui_globals):
    """--no-color forces plain output even on a TTY."""
    make_dep_with_artifact(tmp_path)

    with (
        patch("subprocess.run", side_effect=lambda *a, **k: completed(0)),
        patch.object(sys.stdout, "isatty", return_value=True),
    ):
        run_main(tmp_path, ["--no-color", "demo"])

    out = capsys.readouterr().out
    assert "\033[" not in out
    assert vdeps._UI_COLOR_OVERRIDE is False


def test_color_auto_disabled_when_not_tty(reset_ui_globals):
    """Captured (non-TTY) output stays plain so tests/scripts keep matching."""
    vdeps._UI_COLOR_OVERRIDE = None
    assert vdeps._use_color() is False
    assert "\033[" not in vdeps._tag("INFO", "blue")


def test_no_color_env_disables_color(monkeypatch, reset_ui_globals):
    """NO_COLOR=1 disables color even when stdout claims to be a TTY."""
    monkeypatch.setenv("NO_COLOR", "1")
    vdeps._UI_COLOR_OVERRIDE = None
    with patch.object(sys.stdout, "isatty", return_value=True):
        assert vdeps._use_color() is False


def test_format_tail_truncates():
    """Long logs are trimmed to the last 40 lines with a skip marker."""
    text = "\n".join(f"line {i}" for i in range(50))
    tail = vdeps._format_tail(text)
    assert "... (10 more lines)" in tail
    assert "line 49" in tail
    assert "line 0" not in tail.splitlines()
    assert vdeps._format_tail("") == ""
    assert vdeps._format_tail(None) == ""
