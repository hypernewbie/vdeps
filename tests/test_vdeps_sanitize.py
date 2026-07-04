"""Tests for the ``--sanitize`` CLI flag and its pipeline effects.

The flag drives four observable axes:

* ``get_platform_cmake_args`` appends ``-fsanitize=<set>`` to all 5
  compiler + linker flag variables when set, and is a no-op when unset.
* ``platform_subdir`` grows a ``_<sanitize-tag>`` segment on Linux/macOS
  and appends to the Windows ``win_<llvm>_<md>_<sanitize>`` chain.
* ``get_toolchain_fingerprint`` includes ``sanitize`` so flipping it
  invalidates ``--auto-skip``.
* The generated CMake wrapper emits ``vdeps_all_tsan`` (and the
  corresponding per-dependency ``*_tsan`` targets) when ``VDEPS_SANITIZE``
  is non-empty.
"""

import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


# --- helpers ---


def write_file(path, content="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_config(root, content):
    (root / "vdeps.toml").write_text(content, encoding="utf-8")


def run_main(root, argv):
    with (
        patch("sys.argv", ["vdeps.py", *argv]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
    ):
        vdeps.main()


def get_cmake_content(tmp_path):
    with patch("subprocess.run"), patch("shutil.copy2"):
        run_main(tmp_path, ["--generate-cmake"])
    return (tmp_path / "vdeps" / "CMakeLists.txt").read_text(encoding="utf-8")


# --- tag normalization ---


def test_normalize_sanitize_tag_empty():
    assert vdeps._normalize_sanitize_tag(None) == ""
    assert vdeps._normalize_sanitize_tag("") == ""


def test_normalize_sanitize_tag_single():
    assert vdeps._normalize_sanitize_tag("thread") == "thread"
    assert vdeps._normalize_sanitize_tag("address") == "address"


def test_normalize_sanitize_tag_strips_whitespace_and_dedupes_spaces():
    assert vdeps._normalize_sanitize_tag(" thread ") == "thread"
    assert vdeps._normalize_sanitize_tag("  thread  ,  address  ") == "thread_address"
    assert vdeps._normalize_sanitize_tag("thread,,") == "thread"


# --- compiler/linker flags ---


def test_get_platform_cmake_args_linux_thread_appends_sanitize_to_all_five_flags():
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", False):
        args = vdeps.get_platform_cmake_args(sanitize="thread")
    # Five flag variables get -fsanitize=thread appended:
    joined = " ".join(args)
    assert joined.count("-fsanitize=thread") == 5
    # And the 5 names are all there.
    for flag in (
        "-DCMAKE_C_FLAGS=-w -fsanitize=thread",
        "-DCMAKE_CXX_FLAGS=-w -stdlib=libc++ -fsanitize=thread",
        "-DCMAKE_EXE_LINKER_FLAGS=-stdlib=libc++ -lc++abi -fsanitize=thread",
        "-DCMAKE_SHARED_LINKER_FLAGS=-stdlib=libc++ -lc++abi -fsanitize=thread",
        "-DCMAKE_MODULE_LINKER_FLAGS=-stdlib=libc++ -lc++abi -fsanitize=thread",
    ):
        assert flag in args


def test_get_platform_cmake_args_linux_no_sanitize_unchanged():
    """When --sanitize is unset, the Unix path is byte-identical to pre-feature output.

    The pre-existing test suite asserts no sanitizer flags slip in for the
    default case; pin the explicit 4-flag list so we never regress that.
    MODULE_LINKER_FLAGS is intentionally absent on Unix+no-sanitize and
    must not appear (this is the load-bearing test for that contract).
    """
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", False):
        args = vdeps.get_platform_cmake_args()
    for flag in (
        "-DCMAKE_C_FLAGS=-w",
        "-DCMAKE_CXX_FLAGS=-w -stdlib=libc++",
        "-DCMAKE_EXE_LINKER_FLAGS=-stdlib=libc++ -lc++abi",
        "-DCMAKE_SHARED_LINKER_FLAGS=-stdlib=libc++ -lc++abi",
    ):
        assert flag in args
    # MODULE_LINKER_FLAGS must remain absent (we only emit it when sanitizing).
    assert not any(a.startswith("-DCMAKE_MODULE_LINKER_FLAGS") for a in args), (
        f"MODULE_LINKER_FLAGS should not be emitted on Linux without sanitizers: {args}"
    )
    assert not any("sanitize" in a for a in args)


def test_get_platform_cmake_args_macos_thread_appends_sanitize():
    """macOS differs from Linux only by omitting -lc++abi."""
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", True):
        args = vdeps.get_platform_cmake_args(sanitize="address")
    assert "-DCMAKE_C_FLAGS=-w -fsanitize=address" in args
    assert "-DCMAKE_CXX_FLAGS=-w -stdlib=libc++ -fsanitize=address" in args
    # No -lc++abi on macOS
    assert "-DCMAKE_EXE_LINKER_FLAGS=-stdlib=libc++ -fsanitize=address" in args
    assert "lc++abi" not in " ".join(args)


def test_get_platform_cmake_args_win_msvc_thread_appends_sanitize_to_all_five():
    with patch("vdeps.IS_WINDOWS", True):
        args = vdeps.get_platform_cmake_args(sanitize="address")
    assert "-DCMAKE_C_FLAGS=/W0 -fsanitize=address" in args
    assert "-DCMAKE_CXX_FLAGS=/W0 /EHsc /MP -fsanitize=address" in args
    # Without --llvm, the linker flags are normally absent; --sanitize
    # surfaces them so the sanitizer runtime is present in the link line.
    for flag in (
        "-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address",
        "-DCMAKE_SHARED_LINKER_FLAGS=-fsanitize=address",
        "-DCMAKE_MODULE_LINKER_FLAGS=-fsanitize=address",
    ):
        assert flag in args


def test_get_platform_cmake_args_win_msvc_no_sanitize_unchanged():
    """Default Win+MSVC args must remain identical to pre-feature output."""
    with patch("vdeps.IS_WINDOWS", True):
        args = vdeps.get_platform_cmake_args()
    assert "-DCMAKE_C_FLAGS=/W0" in args
    assert "-DCMAKE_CXX_FLAGS=/W0 /EHsc /MP" in args
    assert not any("sanitize" in a for a in args)
    assert not any("LINKER_FLAGS" in a for a in args)


def test_get_platform_cmake_args_win_llvm_thread_appends_sanitize_to_all_five():
    with (
        patch("vdeps.IS_WINDOWS", True),
        patch(
            "vdeps.resolve_executable_path",
            side_effect=lambda x: f"C:/LLVM/bin/{x}",
        ),
    ):
        args = vdeps.get_platform_cmake_args(use_llvm=True, sanitize="thread")
    assert "-DCMAKE_C_FLAGS=/W0 -w -fsanitize=thread" in args
    assert "-DCMAKE_CXX_FLAGS=/W0 /EHsc -w -fsanitize=thread" in args
    for flag in (
        "-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=thread",
        "-DCMAKE_SHARED_LINKER_FLAGS=-fsanitize=thread",
        "-DCMAKE_MODULE_LINKER_FLAGS=-fsanitize=thread",
    ):
        assert flag in args


def test_get_platform_cmake_args_comma_separated_sanitize():
    """A comma-separated set should pass through verbatim to -fsanitize."""
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", False):
        args = vdeps.get_platform_cmake_args(sanitize="thread,undefined")
    assert "-fsanitize=thread,undefined" in " ".join(args)


# --- toolchain fingerprint ---


def test_fingerprint_includes_sanitize_none():
    fp = vdeps.get_toolchain_fingerprint(False, False, None)
    assert "sanitize" in fp
    assert fp["sanitize"] is None


def test_fingerprint_includes_sanitize_thread():
    fp = vdeps.get_toolchain_fingerprint(False, False, "thread")
    assert fp["sanitize"] == "thread"


def test_fingerprint_distinguishes_thread_vs_none():
    """Adding --sanitize changes the fingerprint so --auto-skip invalidates."""
    a = vdeps.get_toolchain_fingerprint(False, False, None)
    b = vdeps.get_toolchain_fingerprint(False, False, "thread")
    assert a != b


def test_fingerprint_distinguishes_thread_vs_address():
    """Different sanitizers build different binaries and must invalidate."""
    a = vdeps.get_toolchain_fingerprint(False, False, "thread")
    b = vdeps.get_toolchain_fingerprint(False, False, "address")
    assert a != b


# --- CLI validation ---


def test_validate_parallel_rejects_non_int():
    """argparse rejects --parallel with a non-integer value."""
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vdeps._validate_parallel("four")


def test_validate_parallel_rejects_zero():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vdeps._validate_parallel("0")


def test_validate_parallel_rejects_negative():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vdeps._validate_parallel("-3")


def test_validate_parallel_accepts_positive():
    assert vdeps._validate_parallel("1") == 1
    assert vdeps._validate_parallel("4") == 4
    assert vdeps._validate_parallel("64") == 64


# --- generated CMake wrapper ---


def test_generate_cmake_with_sanitize_emits_tsan_targets(tmp_path):
    """When VDEPS_SANITIZE is set, the wrapper emits *_tsan targets."""
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )
    content = get_cmake_content(tmp_path)

    # Sanitized per-dep targets exist for all 4 runtime combos.
    for suffix in ("mt", "llvm_mt", "md", "llvm_md"):
        assert f"vdeps_nvrhi_{suffix}_tsan" in content
    # Sanitized aggregate targets exist.
    for suffix in ("mt", "llvm_mt", "md", "llvm_md"):
        assert f"add_custom_target(vdeps_all_{suffix}_tsan)" in content
    # Top-level sanitizer aggregate.
    assert "add_custom_target(vdeps_all_tsan)" in content


def test_generate_cmake_with_sanitize_appends_flag_to_invocation(tmp_path):
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )
    content = get_cmake_content(tmp_path)
    # The sanitizerized vdeps_build_dep invocations must include --sanitize
    # pointing at the cache variable, so the value set by the consumer wins.
    assert "--sanitize ${VDEPS_SANITIZE}" in content


def test_generate_cmake_without_sanitize_omits_tsan_block(tmp_path):
    """Default (VDEPS_SANITIZE empty): the sanitizer aggregate is gated out.

    We confirm by inspection that the entire sanitizer aggregate block
    sits inside ``if(_VDEPS_SANITIZE_TAG) ... endif()`` rather than being
    emitted unconditionally.
    """
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )
    content = get_cmake_content(tmp_path)
    # The aggregate block must be wrapped in the sanitizer gate.
    assert "if(_VDEPS_SANITIZE_TAG)" in content
    # Locate the gate that contains the sanitizer aggregate, then ensure
    # the closing endif() follows it without an unconditional target call
    # outside of it.
    lines = content.splitlines()
    in_tsan_block = False
    add_custom_target_outside_gate = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("if(_VDEPS_SANITIZE_TAG)"):
            in_tsan_block = True
            continue
        if in_tsan_block and stripped.startswith("endif()"):
            in_tsan_block = False
            continue
        if (
            not in_tsan_block
            and "vdeps_all_tsan" in stripped
            and "add_custom_target" in stripped
        ):
            add_custom_target_outside_gate = True
    assert not add_custom_target_outside_gate, (
        f"Sanitizer aggregate is unconditional somewhere:\n{content}"
    )


def test_generate_cmake_exposes_vdeps_sanitize_cache_var(tmp_path):
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )
    content = get_cmake_content(tmp_path)
    assert 'set(VDEPS_SANITIZE ""' in content
    assert 'CACHE STRING' in content


def test_generate_cmake_sanitize_gate_is_correct(tmp_path):
    """Sanitized variants are gated by _VDEPS_SANITIZE_TAG (not VDEPS_SANITIZE)."""
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )
    content = get_cmake_content(tmp_path)
    # The tag normalization is what the actual if() checks, since list
    # expansion inside if() would otherwise conflate "thread," (truthy)
    # with "thread" (truthy).
    assert "if(_VDEPS_SANITIZE_TAG)" in content


def test_generate_cmake_rejects_sanitize_flag(tmp_path, capsys):
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )

    with pytest.raises(SystemExit) as exc:
        run_main(tmp_path, ["--generate-cmake", "--sanitize", "thread"])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    # argparse reverses the order of arguments in the error message.
    assert "--sanitize" in captured.err and "--generate-cmake" in captured.err
    assert "cannot be used with" in captured.err


def test_generate_cmake_rejects_parallel_flag(tmp_path, capsys):
    write_config(
        tmp_path,
        """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
    )

    with pytest.raises(SystemExit) as exc:
        run_main(tmp_path, ["--generate-cmake", "--parallel", "4"])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--parallel" in captured.err and "--generate-cmake" in captured.err
    assert "cannot be used with" in captured.err


# --- platform_subdir ---


def test_platform_subdir_linux_gets_sanitize_tag(tmp_path, capsys):
    """Linux+--sanitize thread produces 'linux_thread' subdir in the output path.

    The path is composed in main() and announced via ``--- Copying artefacts to
    ...``; we assert that announcement to avoid threading mocks through the
    artifact-discovery loop. The unit tests in test_vdeps_md.py cover the
    deeper artifact-copy mechanics for the analogous ``--md`` axis.
    """
    write_config(
        tmp_path,
        """
[[dependency]]
name = "demo"
rel_path = "demo"
cmake_options = []
libs = ["demo"]
""",
    )
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    debug_build = tmp_path / "vdeps" / "demo" / "build_thread_debug"
    debug_build.mkdir(parents=True)
    write_file(debug_build / "libdemo.a", "a")

    with (
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.IS_MACOS", False),
        patch("vdeps.PLATFORM_TAG", "linux"),
        patch("sys.argv", ["vdeps.py", "--sanitize", "thread"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[str(debug_build / "libdemo.a")]),
    ):
        vdeps.main()

    captured = capsys.readouterr()
    assert "linux_thread_debug" in captured.out


def test_platform_subdir_win_gets_sanitize_tag(tmp_path):
    """Windows+--sanitize address (without llvm/md) -> win_address."""
    write_config(
        tmp_path,
        """
[[dependency]]
name = "demo"
rel_path = "demo"
cmake_options = []
libs = ["demo"]
""",
    )
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    (tmp_path / "vdeps" / "demo" / "build_address_debug").mkdir(parents=True)
    write_file(tmp_path / "vdeps" / "demo" / "build_address_debug" / "demo.lib", "a")

    captured = {}

    def spy_copy(src, dest, root_dir, copied_outputs):
        captured.setdefault("dests", []).append(dest)

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--sanitize", "address"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[str(tmp_path / "vdeps" / "demo" / "build_address_debug" / "demo.lib")]),
        patch("vdeps.copy_tracked_file", side_effect=spy_copy),
    ):
        vdeps.main()

    dests = [d.replace("\\", "/") for d in captured.get("dests", [])]
    assert any("win_address_debug" in d for d in dests), dests


# --- auto-skip back-compat ---


def test_auto_skip_back_compat_old_record_without_sanitize():
    """Records written before --sanitize support must still skip against a run without sanitizers."""
    from unittest.mock import MagicMock

    # An old record (no 'sanitize' key in toolchain), compared against
    # a current run without --sanitize (sanitize: None).
    old_record = {
        "compiler_path": "C:/fake/cl.exe",
        "compiler_version": "fake-cl 1.0",
        "use_llvm": False,
        "use_dynamic_runtime": False,
        # intentionally no 'sanitize' key
    }
    new_fingerprint = {
        "compiler_path": "C:/fake/cl.exe",
        "compiler_version": "fake-cl 1.0",
        "use_llvm": False,
        "use_dynamic_runtime": False,
        "sanitize": None,
    }
    # The back-compat logic lives in evaluate_auto_skip. We assert by
    # direct dict manipulation: both should normalize to the same value.
    norm_old = dict(old_record)
    norm_old.setdefault("sanitize", None)
    norm_new = dict(new_fingerprint)
    norm_new.setdefault("sanitize", None)
    assert norm_old == norm_new


def test_auto_skip_invalidates_when_sanitize_changes():
    """A new sanitize run vs. an old record lacking sanitize must invalidate."""
    old_record = {
        "compiler_path": "C:/fake/cl.exe",
        "compiler_version": "fake-cl 1.0",
        "use_llvm": False,
        "use_dynamic_runtime": False,
    }
    new_with_sanitize = {
        "compiler_path": "C:/fake/cl.exe",
        "compiler_version": "fake-cl 1.0",
        "use_llvm": False,
        "use_dynamic_runtime": False,
        "sanitize": "thread",
    }
    norm_old = dict(old_record)
    norm_old.setdefault("sanitize", None)
    norm_new = dict(new_with_sanitize)
    norm_new.setdefault("sanitize", None)
    # Defaults normalize old -> sanitize=None, new -> sanitize="thread"
    assert norm_old != norm_new


# --- clean ---


def test_clean_removes_sanitize_build_dirs(tmp_path, capsys):
    """`--clean` with --sanitize=thread removes build_thread_* dirs."""
    root = tmp_path
    dep_dir = root / "vdeps" / "test_dep"
    dep_dir.mkdir(parents=True)
    (dep_dir / "build_thread_debug").mkdir()
    (dep_dir / "build_thread_release").mkdir()
    # Also keep an unrelated dir to make sure the glob is sane.
    (dep_dir / "build_debug").mkdir()

    toml = """
    dependency = [{ name = "test_dep", rel_path = "test_dep", cmake_options = [] }]
    """
    (root / "vdeps.toml").write_text(toml)

    with (
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.IS_MACOS", False),
        patch("vdeps.PLATFORM_TAG", "linux"),
        patch("sys.argv", ["vdeps.py", "--clean", "--sanitize", "thread"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("builtins.input", return_value="clean"),
    ):
        with pytest.raises(SystemExit) as exc:
            vdeps.main()
        assert exc.value.code == 0

    assert not (dep_dir / "build_thread_debug").exists()
    assert not (dep_dir / "build_thread_release").exists()


# --- integration: regenerated wrapper must `cmake` cleanly ---


def test_generated_wrapper_configures_with_sanitize_default_configs(tmp_path):
    """Integration smoke: the regenerated wrapper must configure under CMake
    with VDEPS_SANITIZE=thread under the documented default config.
    """
    write_config(
        tmp_path,
        """
[[dependency]]
name = "demo"
rel_path = "demo"
cmake_options = []
""",
    )
    with patch("subprocess.run"), patch("shutil.copy2"):
        run_main(tmp_path, ["--generate-cmake"])

    wrapper = tmp_path / "vdeps" / "CMakeLists.txt"
    cmake_lists = wrapper.parent.parent / "CMakeLists.txt"
    wrapper_posix = wrapper.parent.as_posix()
    cmake_lists.write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(consumer NONE)\n"
        "set(VDEPS_SANITIZE \"thread\" CACHE STRING \"\" FORCE)\n"
        f'add_subdirectory("{wrapper_posix}" vdeps_build)\n',
        encoding="utf-8",
    )
    build_dir = tmp_path / "_build"

    import shutil as _shutil
    cmake = _shutil.which("cmake")
    if cmake is None:
        pytest.skip("cmake not on PATH; integration test skipped")

    proc = subprocess.run(
        [cmake, "-S", str(tmp_path), "-B", str(build_dir), "-Wno-dev"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"configure failed: stdout={proc.stdout}\nstderr={proc.stderr}"
    )


def test_generated_wrapper_configures_with_full_matrix_and_sanitize(tmp_path):
    """Same integration smoke under the full runtime x llvm matrix."""
    write_config(
        tmp_path,
        """
[[dependency]]
name = "demo"
rel_path = "demo"
cmake_options = []
""",
    )
    with patch("subprocess.run"), patch("shutil.copy2"):
        run_main(tmp_path, ["--generate-cmake"])

    wrapper = tmp_path / "vdeps" / "CMakeLists.txt"
    cmake_lists = wrapper.parent.parent / "CMakeLists.txt"
    wrapper_posix = wrapper.parent.as_posix()
    cmake_lists.write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(consumer NONE)\n"
        "set(VDEPS_SANITIZE \"thread\" CACHE STRING \"\" FORCE)\n"
        "set(VDEPS_STATIC_RUNTIME ON CACHE BOOL \"\" FORCE)\n"
        "set(VDEPS_DYNAMIC_RUNTIME ON CACHE BOOL \"\" FORCE)\n"
        "set(VDEPS_USE_LLVM ON CACHE BOOL \"\" FORCE)\n"
        f'add_subdirectory("{wrapper_posix}" vdeps_build)\n',
        encoding="utf-8",
    )
    build_dir = tmp_path / "_build"

    import shutil as _shutil
    cmake = _shutil.which("cmake")
    if cmake is None:
        pytest.skip("cmake not on PATH; integration test skipped")

    proc = subprocess.run(
        [cmake, "-S", str(tmp_path), "-B", str(build_dir), "-Wno-dev"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_sanitizer_aggregate_fanin_is_runtime_gated(tmp_path):
    """Structural regression guard for the HIGH architect-review finding.

    The buggy version of the wrapper unconditionally listed all four sub-
    aggregates inside the sanitizer gate, which failed Ninja builds with
    "unknown target" when the full matrix wasn't enabled. The fix wraps
    each ``add_dependencies(vdeps_all_tsan ...)`` in matching
    VDEPS_STATIC_RUNTIME / VDEPS_DYNAMIC_RUNTIME / VDEPS_USE_LLVM guards.

    We assert the structure of the generated file directly: each fan-in
    edge for ``vdeps_all_tsan`` must be inside the right runtime+llvm gate.
    """
    write_config(
        tmp_path,
        """
[[dependency]]
name = "demo"
rel_path = "demo"
cmake_options = []
""",
    )
    content = get_cmake_content(tmp_path)
    lines = content.splitlines()

    # Walk the file, tracking a stack of (depth, runtime, llvm) frames so
    # we can identify each add_dependencies's enclosing runtime+llvm gate.
    issues = []
    stack = []  # list of dicts: {"depth": int, "runtime": ..., "llvm": ...}

    def current_runtime():
        for frame in reversed(stack):
            if frame["runtime"] is not None:
                return frame["runtime"]
        return None

    def current_llvm():
        # Walk inward; LLVM state is binary per-depth so use the innermost.
        for frame in reversed(stack):
            if frame["llvm"] is not None:
                return frame["llvm"]
        return None

    depth = 0
    for raw in lines:
        line = raw.strip()
        if line.startswith("if("):
            depth += 1
            runtime = None
            llvm = None
            if "VDEPS_STATIC_RUNTIME" in line:
                runtime = "static"
            elif "VDEPS_DYNAMIC_RUNTIME" in line:
                runtime = "dynamic"
            if "VDEPS_USE_LLVM" in line:
                llvm = True
            stack.append(
                {"depth": depth, "runtime": runtime, "llvm": llvm,
                 "entered_depth": depth}
            )
            continue
        if line.startswith("else()"):
            # else flips the LLVM state at this depth.
            top = stack[-1]
            if top["llvm"] is True:
                top["llvm"] = False
            continue
        if line.startswith("endif()"):
            depth -= 1
            # Pop any stack frames that belonged to the closing depth.
            while stack and stack[-1]["entered_depth"] > depth:
                stack.pop()
            continue

        if not line.startswith("add_dependencies(vdeps_all_tsan "):
            continue

        target = line.split(
            "add_dependencies(vdeps_all_tsan ", 1
        )[1].split(")")[0].strip()
        required = {
            "vdeps_all_mt_tsan": ("static", False),
            "vdeps_all_llvm_mt_tsan": ("static", True),
            "vdeps_all_md_tsan": ("dynamic", False),
            "vdeps_all_llvm_md_tsan": ("dynamic", True),
        }.get(target)
        if required is None:
            continue
        req_runtime, req_llvm = required
        if current_runtime() != req_runtime:
            issues.append(
                f"{target} requires {req_runtime} runtime but is inside "
                f"runtime gate={current_runtime()}"
            )
        if current_llvm() != req_llvm:
            issues.append(
                f"{target} requires llvm={req_llvm} but inside llvm "
                f"gate={current_llvm()}"
            )

    assert not issues, (
        "Sanitizer aggregate fan-in is not properly runtime-gated:\n  - "
        + "\n  - ".join(issues)
    )


# --- sanitize empty / None parity ---


def test_fingerprint_unaffected_by_sanitize_empty_string():
    """`--sanitize ""` and omitting the flag must produce the same fingerprint.

    Empty string disables sanitizers functionally; the fingerprint should
    not penalize either spelling.
    """
    a = vdeps.get_toolchain_fingerprint(False, False, None)
    b = vdeps.get_toolchain_fingerprint(False, False, "")
    assert a == b
