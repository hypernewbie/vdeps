"""Tests for the ``--arch`` CLI flag and its pipeline effects.

The flag drives four observable axes:

* ``get_platform_cmake_args`` emits ``-DCMAKE_OSX_ARCHITECTURES=<arch>``
  on macOS when set; ignored on non-macOS hosts.
* ``platform_subdir`` grows a ``_<arch-tag>`` segment on macOS.
* ``get_toolchain_fingerprint`` includes ``arch`` so flipping it
  invalidates ``--auto-skip`` (back-compat: records written before
  ``--arch`` support lacked the key and validate as ``arch=None``).
* The generated CMake wrapper exposes a ``VDEPS_ARCH`` cache var and
  threads ``--arch ${VDEPS_ARCH}`` through every ``vdeps_build_dep``
  invocation, guarded by ``if(VDEPS_ARCH)`` so the empty default
  doesn't emit a bare ``--arch`` token that crashes argparse.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


# --- helpers ---


SINGLE_DEP_TOML = (
    '[[dependency]]\n'
    'name = "x"\n'
    'rel_path = "x"\n'
    'libs = ["x"]\n'
    'cmake_options = []\n'
)


def write_config(root, content):
    (root / "vdeps.toml").write_text(content, encoding="utf-8")


def run_main(root, argv):
    with (
        patch("sys.argv", ["vdeps.py", *argv]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
    ):
        vdeps.main()


def get_cmake_content(tmp_path):
    write_config(tmp_path, SINGLE_DEP_TOML)
    run_main(tmp_path, ["--generate-cmake"])
    return (tmp_path / "vdeps" / "CMakeLists.txt").read_text(encoding="utf-8")


def make_parser():
    """Build the same parser shape as vdeps.main() for validate_* tests."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", type=vdeps._validate_arch, default=None)
    parser.add_argument("--generate-cmake", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--auto-skip", action="store_true")
    parser.add_argument("--llvm", action="store_true")
    parser.add_argument("--sanitize", default=None)
    parser.add_argument("--parallel", type=vdeps._validate_parallel, default=None)
    parser.add_argument("--md", action="store_true")
    parser.add_argument("dependencies", nargs="*")
    return parser


def run_with_patches(argv, **patches):
    """Run vdeps.main() with IS_MACOS/IS_WINDOWS patched + cwd/vdeps file mocked."""
    defaults = {
        "vdeps.os.path.dirname": str(Path.cwd()),
        "vdeps.os.path.abspath": str(Path.cwd() / "vdeps.py"),
        "vdeps.run_command": lambda *a, **k: None,
        "glob.glob": [],
        "shutil.copy2": lambda *a, **k: None,
    }
    defaults.update(patches)
    ctx = [patch("sys.argv", ["vdeps.py", *argv]),
           patch("vdeps.__file__", str(Path.cwd() / "vdeps.py"))]
    for target, value in defaults.items():
        ctx.append(patch(target, value) if not callable(value) else patch(target, side_effect=value))
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        vdeps.main()


from contextlib import ExitStack


# --- _normalize_arch / _validate_arch ---


@pytest.mark.parametrize(
    "value,expected_tag,expected_cmake",
    [
        # canonical aliases
        ("arm64", "arm64", "arm64"),
        ("aarch64", "arm64", "arm64"),
        ("x64", "x64", "x86_64"),
        ("x86_64", "x64", "x86_64"),
        ("amd64", "x64", "x86_64"),
        # case-insensitive
        ("ARM64", "arm64", "arm64"),
        ("AArch64", "arm64", "arm64"),
        ("X86_64", "x64", "x86_64"),
        ("X64", "x64", "x86_64"),
        ("AMD64", "x64", "x86_64"),
        # whitespace tolerant
        ("  arm64  ", "arm64", "arm64"),
        ("\tx64\n", "x64", "x86_64"),
        # empty / None / falsy -> empty pair
        ("", "", ""),
        (None, "", ""),
    ],
)
def test_normalize_arch_returns_canonical_pair(value, expected_tag, expected_cmake):
    assert vdeps._normalize_arch(value) == (expected_tag, expected_cmake)


@pytest.mark.parametrize(
    "value",
    [
        "i386",
        "riscv64",
        "ppc64le",
        "arm",  # bare 'arm' not supported (armv7 etc)
        "universal",  # reserved for future, not accepted today
        "x86",  # only 32-bit x86 disallowed
        "arm64;x86_64",  # universal binaries foreclosed (per architect)
    ],
)
def test_normalize_arch_rejects_unsupported(value):
    with pytest.raises(ValueError, match="unsupported --arch"):
        vdeps._normalize_arch(value)


def test_validate_arch_returns_display_tag():
    """_validate_arch returns just the display tag (or None) for argparse."""
    assert vdeps._validate_arch("arm64") == "arm64"
    assert vdeps._validate_arch("x86_64") == "x64"
    assert vdeps._validate_arch("AMD64") == "x64"
    assert vdeps._validate_arch("") is None
    # argparse catches the error before this returns, but we still raise
    # the right exception type when called directly.
    with pytest.raises(argparse.ArgumentTypeError, match="unsupported --arch"):
        vdeps._validate_arch("garbage")


# --- get_platform_cmake_args arch kwarg ---


def test_get_platform_cmake_args_mac_arm64_emits_architectures():
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", True):
        args = vdeps.get_platform_cmake_args(arch="arm64")
    assert "-DCMAKE_OSX_ARCHITECTURES=arm64" in args


def test_get_platform_cmake_args_mac_x86_64_emits_architectures_canonical():
    """The cmake_arch value is what CMake expects: arm64 / x86_64 (not x64)."""
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", True):
        args = vdeps.get_platform_cmake_args(arch="x86_64")
    assert "-DCMAKE_OSX_ARCHITECTURES=x86_64" in args
    # The short 'x64' is the dir-name form; CMake never sees it.
    assert not any("CMAKE_OSX_ARCHITECTURES=x64" == a for a in args), (
        f"CMake must get canonical x86_64, not the dir-tag x64: {args}"
    )


def test_get_platform_cmake_args_mac_no_arch_emits_nothing():
    """Default arch is empty: no CMAKE_OSX_ARCHITECTURES flag emitted (preserves byte-identical default)."""
    for call in (
        lambda: vdeps.get_platform_cmake_args(),
        lambda: vdeps.get_platform_cmake_args(arch=None),
        lambda: vdeps.get_platform_cmake_args(arch=""),
    ):
        with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", True):
            args = call()
        assert not any("CMAKE_OSX_ARCHITECTURES" in a for a in args), (
            f"Expected no CMAKE_OSX_ARCHITECTURES for empty arch: {args}"
        )


def test_get_platform_cmake_args_linux_arch_is_ignored():
    """Architectures is a macOS concept; on Linux the arch kwarg is a no-op."""
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", False):
        args = vdeps.get_platform_cmake_args(arch="x86_64")
    assert not any("CMAKE_OSX_ARCHITECTURES" in a for a in args)


def test_get_platform_cmake_args_windows_arch_is_ignored():
    """Architectures is a macOS concept; on Windows the arch kwarg is a no-op."""
    with patch("vdeps.IS_WINDOWS", True), patch("vdeps.IS_MACOS", False):
        args = vdeps.get_platform_cmake_args(arch="x86_64")
    assert not any("CMAKE_OSX_ARCHITECTURES" in a for a in args)


def test_get_platform_cmake_args_mac_arch_composes_with_sanitize():
    """Arch and sanitize coexist on the cmake command line."""
    with patch("vdeps.IS_WINDOWS", False), patch("vdeps.IS_MACOS", True):
        args = vdeps.get_platform_cmake_args(arch="x86_64", sanitize="thread")
    assert "-DCMAKE_OSX_ARCHITECTURES=x86_64" in args
    assert any("-fsanitize=thread" in a for a in args)


# --- get_toolchain_fingerprint arch kwarg ---


def test_toolchain_fingerprint_includes_arch():
    fp = vdeps.get_toolchain_fingerprint(use_llvm=False, use_dynamic_runtime=False, arch="x64")
    assert fp["arch"] == "x64"


def test_toolchain_fingerprint_arch_normalizes_falsy_to_none():
    """Empty string and None both serialize to None so --arch "" matches omitted."""
    assert vdeps.get_toolchain_fingerprint(False, False, arch=None)["arch"] is None
    assert vdeps.get_toolchain_fingerprint(False, False, arch="")["arch"] is None
    assert vdeps.get_toolchain_fingerprint(False, False, arch="x64")["arch"] == "x64"


def test_toolchain_fingerprint_arch_differs_from_sanitize():
    """Arch is its own field; doesn't collide with sanitize normalization."""
    fp_clean = vdeps.get_toolchain_fingerprint(False, False)
    fp_arch = vdeps.get_toolchain_fingerprint(False, False, arch="x64")
    fp_sanitize = vdeps.get_toolchain_fingerprint(False, False, sanitize="thread")
    fp_both = vdeps.get_toolchain_fingerprint(False, False, sanitize="thread", arch="x64")
    assert fp_clean != fp_arch
    assert fp_clean != fp_sanitize
    assert fp_arch != fp_sanitize
    assert fp_both["sanitize"] == "thread"
    assert fp_both["arch"] == "x64"


# --- validate_cli_args macOS-only check ---


def test_validate_cli_args_rejects_arch_on_windows():
    """`--arch x64` on a non-macOS host exits with an error."""
    parser = make_parser()
    args = parser.parse_args(["--arch", "x64"])
    with patch("vdeps.IS_MACOS", False), patch("vdeps.IS_WINDOWS", True):
        with pytest.raises(SystemExit):
            vdeps.validate_cli_args(args, parser)


def test_validate_cli_args_accepts_arch_on_macos():
    """`--arch x64` on macOS is accepted."""
    parser = make_parser()
    args = parser.parse_args(["--arch", "x64"])
    with patch("vdeps.IS_MACOS", True), patch("vdeps.IS_WINDOWS", False):
        # Should not raise.
        vdeps.validate_cli_args(args, parser)


def test_validate_cli_args_arch_unset_is_noop_everywhere():
    """`--arch` not passed -> arch tag is None -> no platform check fires."""
    parser = make_parser()
    args = parser.parse_args([])
    with patch("vdeps.IS_MACOS", False), patch("vdeps.IS_WINDOWS", True):
        # Should not raise -- unset arch means no platform rejection.
        vdeps.validate_cli_args(args, parser)


# --- validate_generate_cmake_args rejects --arch ---


def test_generate_cmake_rejects_arch_flag(tmp_path, capsys):
    """--generate-cmake --arch must error (mirrors --sanitize / --parallel rejection)."""
    write_config(tmp_path, SINGLE_DEP_TOML)
    with pytest.raises(SystemExit) as exc:
        run_main(tmp_path, ["--generate-cmake", "--arch", "x64"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--arch" in captured.err or "--generate-cmake" in captured.err


# --- platform_subdir (via main loop) ---


def _make_dep_dir(tmp_path):
    """vdeps looks for deps under root/vdeps/<rel_path>, not root/<rel_path>."""
    dep = tmp_path / "vdeps" / "x"
    dep.mkdir(parents=True)
    return dep


def test_platform_subdir_includes_arch_on_macos(tmp_path):
    """`vdeps.py --arch x64` on macOS produces platform_subdir=mac_x64."""
    write_config(tmp_path, SINGLE_DEP_TOML)
    _make_dep_dir(tmp_path)
    with (
        patch("sys.argv", ["vdeps.py", "--arch", "x64"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", True),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "mac"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[]),
        patch("shutil.copy2", side_effect=lambda *a, **k: None),
    ):
        vdeps.main()
    expected_lib = tmp_path / "lib" / "mac_x64_debug"
    assert expected_lib.exists(), f"Expected {expected_lib} to be created with --arch x64"


def test_platform_subdir_unmodified_when_arch_omitted(tmp_path):
    """No --arch on macOS: platform_subdir stays as 'mac' (backward compat)."""
    write_config(tmp_path, SINGLE_DEP_TOML)
    _make_dep_dir(tmp_path)
    with (
        patch("sys.argv", ["vdeps.py"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", True),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "mac"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[]),
        patch("shutil.copy2", side_effect=lambda *a, **k: None),
    ):
        vdeps.main()
    expected_lib = tmp_path / "lib" / "mac_debug"
    assert expected_lib.exists(), f"Default arch (omitted) must produce mac_debug: {expected_lib}"


def test_explicit_arch_arm64_on_arm64_host_produces_mac_arm64(tmp_path):
    """Locks in the 'explicit always adds suffix' contract on macOS.

    A future contributor must not 'helpfully' normalize --arch arm64 back
    to bare mac_* on the arm64 host -- the path is deterministic per CLI
    invocation, not per host.
    """
    write_config(tmp_path, SINGLE_DEP_TOML)
    _make_dep_dir(tmp_path)
    with (
        patch("sys.argv", ["vdeps.py", "--arch", "arm64"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", True),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "mac"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[]),
        patch("shutil.copy2", side_effect=lambda *a, **k: None),
    ):
        vdeps.main()
    assert (tmp_path / "lib" / "mac_arm64_debug").exists()
    assert not (tmp_path / "lib" / "mac_debug").exists(), (
        "Explicit --arch arm64 must NOT fall back to bare mac_* -- "
        "explicit values always add the suffix"
    )


def test_platform_subdir_arch_composes_with_sanitize(tmp_path):
    """Order: arch BEFORE sanitize -- mac_x64_thread_debug."""
    write_config(tmp_path, SINGLE_DEP_TOML)
    _make_dep_dir(tmp_path)
    with (
        patch("sys.argv", ["vdeps.py", "--arch", "x64", "--sanitize", "thread"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", True),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "mac"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[]),
        patch("shutil.copy2", side_effect=lambda *a, **k: None),
    ):
        vdeps.main()
    assert (tmp_path / "lib" / "mac_x64_thread_debug").exists()


def test_arch_rejected_on_linux(tmp_path):
    """--arch on Linux is rejected at CLI; the platform check fires before any work."""
    write_config(tmp_path, SINGLE_DEP_TOML)
    with (
        patch("sys.argv", ["vdeps.py", "--arch", "x64"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", False),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "linux"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[]),
        patch("shutil.copy2", side_effect=lambda *a, **k: None),
    ):
        with pytest.raises(SystemExit):
            vdeps.main()


# --- ${PLATFORM_SUBDIR} interpolation ---


def test_platform_subdir_interpolation_in_cmake_options(tmp_path):
    """A cmake_options entry containing ${PLATFORM_SUBDIR} resolves to mac_x64 under --arch x64."""
    write_config(
        tmp_path,
        SINGLE_DEP_TOML.replace('cmake_options = []\n', 'cmake_options = ["-DFOO=${PLATFORM_SUBDIR}"]\n'),
    )
    _make_dep_dir(tmp_path)
    captured_args = []

    def fake_run(cmd, cwd=None, env=None):
        if cmd and cmd[0] == "cmake" and any("-DFOO=" in a for a in cmd):
            captured_args.append(cmd)

    with (
        patch("sys.argv", ["vdeps.py", "--arch", "x64"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", True),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "mac"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command", side_effect=fake_run),
        patch("glob.glob", return_value=[]),
        patch("shutil.copy2", side_effect=lambda *a, **k: None),
    ):
        vdeps.main()
    assert any("-DFOO=mac_x64" in a for cmd in captured_args for a in cmd), (
        f"Expected -DFOO=mac_x64 in cmake args; got: {captured_args}"
    )
    # Architect finding #3: pin the canonical CMAKE_OSX_ARCHITECTURES value
    # ('x86_64', not 'x64') in main()'s emitted cmake command. A regression
    # swapping arch=arch_cmake for arch=arch_tag would ship
    # CMAKE_OSX_ARCHITECTURES=x64 (invalid) and slip past unit tests.
    assert any("-DCMAKE_OSX_ARCHITECTURES=x86_64" in a for cmd in captured_args for a in cmd), (
        f"Expected -DCMAKE_OSX_ARCHITECTURES=x86_64 (canonical, not x64) in cmake args; "
        f"got: {captured_args}"
    )


def test_platform_subdir_interpolation_in_install_rules(tmp_path):
    """An install rule target containing ${PLATFORM_SUBDIR} resolves to mac_x64 under --arch x64."""
    write_config(
        tmp_path,
        (
            '[[dependency]]\n'
            'name = "x"\n'
            'rel_path = "x"\n'
            'libs = ["x"]\n'
            'cmake_options = []\n'
            'install = [{ pattern = "bin/*", target = "tools/${PLATFORM_SUBDIR}" }]\n'
        ),
    )
    dep_dir = tmp_path / "vdeps" / "x"
    dep_dir.mkdir(parents=True)
    (dep_dir / "bin").mkdir(parents=True)
    tool_src = dep_dir / "bin" / "tool.exe"
    tool_src.write_text("x")

    # Return the actual tool.exe for the install-rule glob call, but empty
    # for everything else (lib search, etc.).
    real_glob = __import__("glob").glob
    real_copy2 = shutil.copy2

    def smart_glob(pattern, *args, **kwargs):
        if "bin/*" in pattern:
            return [str(tool_src)]
        return real_glob(pattern, *args, **kwargs)

    with (
        patch("sys.argv", ["vdeps.py", "--arch", "x64"]),
        patch("vdeps.__file__", str(tmp_path / "vdeps.py")),
        patch("vdeps.IS_MACOS", True),
        patch("vdeps.IS_WINDOWS", False),
        patch("vdeps.PLATFORM_TAG", "mac"),
        patch("vdeps.os.path.dirname", return_value=str(tmp_path)),
        patch("vdeps.os.path.abspath", return_value=str(tmp_path / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", side_effect=smart_glob),
        patch("shutil.copy2", side_effect=real_copy2),
    ):
        vdeps.main()
    # tools/${PLATFORM_SUBDIR} -> tools/mac_x64, which is appended to
    # output_tools_dir = tools/mac_x64_debug/ -> final dest is
    # tools/mac_x64_debug/mac_x64/tool.exe
    assert (tmp_path / "tools" / "mac_x64_debug" / "mac_x64" / "tool.exe").exists(), (
        "Install rule target=${PLATFORM_SUBDIR} must resolve under --arch x64"
    )


# --- Generated CMake wrapper ---


def test_wrapper_declares_vdeps_arch_cache_var(tmp_path):
    """VDEPS_ARCH cache var must be declared with the right type and default."""
    content = get_cmake_content(tmp_path)
    assert 'set(VDEPS_ARCH "" CACHE STRING' in content
    assert "vdeps.py --arch" in content


def test_wrapper_threads_arch_through_vdeps_build_dep(tmp_path):
    """Every vdeps_build_dep EXTRA_ARGS uses ${_VDEPS_EXTRA_ARGV} (the macro that builds --arch inside its guards)."""
    content = get_cmake_content(tmp_path)
    import re
    calls = re.findall(r"vdeps_build_dep\([^)]*\)", content)
    assert calls, "Expected at least one vdeps_build_dep call"
    for call in calls:
        assert "${_VDEPS_EXTRA_ARGV}" in call, (
            f"vdeps_build_dep must use ${{_VDEPS_EXTRA_ARGV}}: {call}"
        )


def test_wrapper_no_bare_arch_token_outside_guard(tmp_path):
    """Architect blocker regression: --arch must NOT appear without an if(VDEPS_ARCH) guard.

    An inline '--arch ${VDEPS_ARCH}' would expand to bare '--arch' when
    VDEPS_ARCH is empty, crash argparse on the receiving end. We track
    `if(VDEPS_ARCH)` nesting depth and assert every
    `set(_VDEPS_EXTRA_ARGV "... --arch ${VDEPS_ARCH}")` line is inside one.
    The `set(VDEPS_ARCH "" CACHE STRING "... --arch ...")` declaration is
    exempt (it's a cache-var help string, not a flag emission).
    """
    import re
    content = get_cmake_content(tmp_path)
    arch_set_re = re.compile(r'set\(_VDEPS_EXTRA_ARGV "[^"]*--arch')
    arch_depth = 0
    offending = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "if(VDEPS_ARCH)":
            arch_depth += 1
            continue
        if stripped == "endif()":
            if arch_depth > 0:
                arch_depth -= 1
            continue
        if not arch_set_re.search(line):
            continue
        offending.append((arch_depth, line))
    unguarded = [(d, l) for d, l in offending if d == 0]
    assert unguarded == [], (
        "Every `set(_VDEPS_EXTRA_ARGV \"... --arch ...\")` line must sit inside "
        "if(VDEPS_ARCH) so an empty VDEPS_ARCH doesn't expand to a bare token. "
        "Offending lines (depth=0):\n"
        + "\n".join(f"  depth={d}: {l!r}" for d, l in unguarded)
    )


def test_wrapper_no_unconditional_arch_token(tmp_path):
    """Stricter version of the guard regression: vdeps_build_dep invocations
    must not embed a literal `--arch ${VDEPS_ARCH}` token at all (only the
    guarded `_VDEPS_EXTRA_ARGV` macro)."""
    content = get_cmake_content(tmp_path)
    import re
    calls = re.findall(r"vdeps_build_dep\([^)]*\)", content)
    for call in calls:
        assert "--arch ${VDEPS_ARCH}" not in call, (
            f"vdeps_build_dep must reference _VDEPS_EXTRA_ARGV, not inline --arch: {call}"
        )


def test_wrapper_arch_composes_with_parallel_and_sanitize(tmp_path):
    """Sanitized variant: arch and parallel appends coexist with --sanitize."""
    write_config(tmp_path, SINGLE_DEP_TOML)
    content = get_cmake_content(tmp_path)
    # Find the first sanitized variant block (the 'if(_VDEPS_SANITIZE_TAG)' opener
    # up to the matching sequence of 4 endif()s). Simplify: check that all
    # three guards appear together in the file and that --sanitize sits
    # alongside them.
    assert "if(_VDEPS_SANITIZE_TAG)" in content
    assert "--sanitize ${VDEPS_SANITIZE}" in content
    assert "if(VDEPS_PARALLEL)" in content
    assert "if(VDEPS_ARCH)" in content
    # And the order inside the sanitized block is consistent.
    san_idx = content.index("if(_VDEPS_SANITIZE_TAG)")
    sanitize_set = content.index('set(_VDEPS_EXTRA_ARGV "', san_idx)
    parallel_if = content.index("if(VDEPS_PARALLEL)", sanitize_set)
    arch_if = content.index("if(VDEPS_ARCH)", sanitize_set)
    assert parallel_if < arch_if, (
        f"VDEPS_PARALLEL guard must precede VDEPS_ARCH guard inside sanitized block: "
        f"sanitize_set={sanitize_set}, parallel_if={parallel_if}, arch_if={arch_if}"
    )


def test_wrapper_no_arch_target_suffix_multiplication(tmp_path):
    """Arch is a --parallel-class axis (modifier), not a --sanitize-class (multiplier).

    Targets should not gain _arm64 / _x64 suffixes, and no vdeps_all_arm64 /
    vdeps_all_x64 aggregate should be created. Only the sanitizer axis
    multiplies the target matrix.
    """
    content = get_cmake_content(tmp_path)
    assert "vdeps_all_arm64" not in content
    assert "vdeps_all_x64" not in content
    assert "_arm64_tsan" not in content
    assert "_x64_tsan" not in content


# --- evaluate_auto_skip back-compat ---


def test_evaluate_auto_skip_old_record_missing_arch_validates_against_no_arch(tmp_path):
    """A pre-arch record (no 'arch' key) validates against a current run with no --arch."""
    from vdeps import (
        Dependency,
        evaluate_auto_skip,
        empty_state_data,
        update_state_record,
    )
    dep = Dependency(name="x", rel_path="x", libs=["x"], cmake_options=[])
    dep_dir = tmp_path / "vdeps" / "x"
    dep_dir.mkdir(parents=True)
    state_data = empty_state_data()
    # Pre-arch record: toolchain dict without 'arch'. Use a toolchain shape
    # that matches what get_toolchain_fingerprint produces on this host
    # (so the comparison isolates the 'arch' field rather than e.g.
    # compiler_path differences).
    real_fp = vdeps.get_toolchain_fingerprint(False, False, None, None)
    record_toolchain = dict(real_fp)
    record_toolchain.pop("arch", None)  # remove 'arch' to simulate pre-arch record
    update_state_record(
        state_data, "x", "x", "mac", "debug",
        toolchain=record_toolchain,
        head="abc123",
        outputs=["lib/mac_debug/x.a"],
    )
    (tmp_path / "lib" / "mac_debug").mkdir(parents=True)
    (tmp_path / "lib" / "mac_debug" / "x.a").write_text("x")

    # Current fingerprint: no --arch -> arch=None. Should validate.
    current_fp = vdeps.get_toolchain_fingerprint(False, False, None, None)
    with patch("vdeps.IS_MACOS", True), patch("vdeps.IS_WINDOWS", False):
        should_skip, reason = evaluate_auto_skip(
            dep, dep_dir, tmp_path, state_data,
            "mac", "debug", "abc123", None, False, current_fp,
        )
    assert should_skip, f"Old record (no arch) + current run (no arch) should auto-skip: {reason}"


def test_evaluate_auto_skip_arch_change_invalidates_old_record(tmp_path):
    """Pre-arch record + current run with --arch x64 -> rebuild (arch mismatch)."""
    from vdeps import (
        Dependency,
        evaluate_auto_skip,
        empty_state_data,
        update_state_record,
    )
    dep = Dependency(name="x", rel_path="x", libs=["x"], cmake_options=[])
    dep_dir = tmp_path / "vdeps" / "x"
    dep_dir.mkdir(parents=True)
    state_data = empty_state_data()
    real_fp = vdeps.get_toolchain_fingerprint(False, False, None, None)
    record_toolchain = dict(real_fp)
    record_toolchain.pop("arch", None)
    update_state_record(
        state_data, "x", "x", "mac", "debug",
        toolchain=record_toolchain,
        head="abc123",
        outputs=["lib/mac_debug/x.a"],
    )
    (tmp_path / "lib" / "mac_debug").mkdir(parents=True)
    (tmp_path / "lib" / "mac_debug" / "x.a").write_text("x")

    # Current fingerprint: --arch x64 -> arch="x64".
    current_fp = vdeps.get_toolchain_fingerprint(False, False, None, "x64")
    with patch("vdeps.IS_MACOS", True), patch("vdeps.IS_WINDOWS", False):
        should_skip, reason = evaluate_auto_skip(
            dep, dep_dir, tmp_path, state_data,
            "mac", "debug", "abc123", None, False, current_fp,
        )
    assert not should_skip
    assert "toolchain changed" in reason


def test_evaluate_auto_skip_arch_x64_then_no_arch_invalidates(tmp_path):
    """Switching from --arch x64 (cached record) to no --arch (current) invalidates."""
    from vdeps import (
        Dependency,
        evaluate_auto_skip,
        empty_state_data,
        update_state_record,
    )
    dep = Dependency(name="x", rel_path="x", libs=["x"], cmake_options=[])
    dep_dir = tmp_path / "vdeps" / "x"
    dep_dir.mkdir(parents=True)
    state_data = empty_state_data()
    record_toolchain = dict(vdeps.get_toolchain_fingerprint(False, False, None, "x64"))
    record_toolchain["arch"] = "x64"
    update_state_record(
        state_data, "x", "x", "mac_x64", "debug",
        toolchain=record_toolchain,
        head="abc123",
        outputs=["lib/mac_x64_debug/x.a"],
    )
    (tmp_path / "lib" / "mac_x64_debug").mkdir(parents=True)
    (tmp_path / "lib" / "mac_x64_debug" / "x.a").write_text("x")

    # Current run: no --arch -> arch=None -> should invalidate.
    current_fp = vdeps.get_toolchain_fingerprint(False, False, None, None)
    with patch("vdeps.IS_MACOS", True), patch("vdeps.IS_WINDOWS", False):
        should_skip, reason = evaluate_auto_skip(
            dep, dep_dir, tmp_path, state_data,
            "mac_x64", "debug", "abc123", None, False, current_fp,
        )
    assert not should_skip
    assert "toolchain changed" in reason


# --- get_state_record_key arch distinctness (locks in Q4/Q5 reasoning) ---


def test_state_record_key_distinguishes_arch():
    """Same dep, same config, different arch -> different state record keys.

    Locks in the design decision: arch flows through platform_subdir into
    the state record key, so an arm64 record never collides with an x64
    record. (Per architect: do NOT add arch as a dedicated key field --
    that would orphan all existing state on every platform.)
    """
    arm64_key = vdeps.get_state_record_key("x", "x", "mac", "debug")
    x64_key = vdeps.get_state_record_key("x", "x", "mac_x64", "debug")
    assert arm64_key != x64_key
    # And the inverse: same platform_subdir -> same key (arch fingerprint
    # is the secondary defense).
    assert vdeps.get_state_record_key("x", "x", "mac", "debug") == \
           vdeps.get_state_record_key("x", "x", "mac", "debug")
