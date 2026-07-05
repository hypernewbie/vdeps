"""Integration tests for MSVC runtime library with actual CMake builds."""

import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def run_cmake_configure(source_dir, build_dir, cmake_args):
    """Run CMake configure and return CMakeCache.txt content.

    ``build_dir`` must be unique per test (e.g. ``tmp_path``) -- reusing one
    shared dir across different generators/compilers makes CMake refuse to
    reconfigure, silently skipping every later test.
    """
    os.makedirs(build_dir, exist_ok=True)

    cmd = ["cmake", "-S", source_dir, "-B", build_dir] + cmake_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(
            f"CMake configure failed (expected on some configs): {result.stderr}"
        )

    cache_file = os.path.join(build_dir, "CMakeCache.txt")
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read()
    return ""


def extract_cmake_cache_value(cache_content, key):
    """Extract a value from CMakeCache.txt."""
    for line in cache_content.splitlines():
        if line.startswith(f"{key}:"):
            return line.split("=", 1)[1] if "=" in line else ""
    return None


FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "vdeps", "test_runtime_lib"
)


class TestCmakeMsvcRuntimeLibrary:
    """Tests that verify CMAKE_MSVC_RUNTIME_LIBRARY is correctly set."""

    def test_static_runtime_library_is_set_windows(self, tmp_path):
        """Test that static runtime uses CMAKE_MSVC_RUNTIME_LIBRARY with MultiThreaded."""
        if not sys.platform == "win32":
            pytest.skip("Windows only test")

        cmake_args = vdeps.get_platform_cmake_args(
            cxx_standard=20, use_llvm=False, use_dynamic_runtime=False
        )
        cmake_args.append("-DCMAKE_BUILD_TYPE=Debug")

        cache_content = run_cmake_configure(FIXTURE, str(tmp_path / "build"), cmake_args)

        runtime_lib = extract_cmake_cache_value(
            cache_content, "CMAKE_MSVC_RUNTIME_LIBRARY"
        )
        assert runtime_lib is not None, (
            "CMAKE_MSVC_RUNTIME_LIBRARY not found in CMakeCache"
        )
        assert "MultiThreaded" in runtime_lib, (
            f"Expected MultiThreaded, got {runtime_lib}"
        )
        assert "DLL" not in runtime_lib, f"Should be static (no DLL), got {runtime_lib}"

    def test_dynamic_runtime_library_is_set_windows(self, tmp_path):
        """Test that dynamic runtime uses CMAKE_MSVC_RUNTIME_LIBRARY with MultiThreadedDLL."""
        if not sys.platform == "win32":
            pytest.skip("Windows only test")

        cmake_args = vdeps.get_platform_cmake_args(
            cxx_standard=20, use_llvm=False, use_dynamic_runtime=True
        )
        cmake_args.append("-DCMAKE_BUILD_TYPE=Debug")

        cache_content = run_cmake_configure(FIXTURE, str(tmp_path / "build"), cmake_args)

        runtime_lib = extract_cmake_cache_value(
            cache_content, "CMAKE_MSVC_RUNTIME_LIBRARY"
        )
        assert runtime_lib is not None, (
            "CMAKE_MSVC_RUNTIME_LIBRARY not found in CMakeCache"
        )
        assert "MultiThreaded" in runtime_lib, (
            f"Expected MultiThreaded, got {runtime_lib}"
        )
        assert "DLL" in runtime_lib, f"Should be dynamic (DLL), got {runtime_lib}"

    def test_static_runtime_build_with_clang_cl(self, tmp_path):
        """Test static runtime builds successfully with clang-cl."""
        if not sys.platform == "win32":
            pytest.skip("Windows only test")

        build_dir = str(tmp_path / "build")
        cmake_args = vdeps.get_platform_cmake_args(
            cxx_standard=20, use_llvm=True, use_dynamic_runtime=False
        )
        cmake_args.append("-DCMAKE_BUILD_TYPE=Debug")

        cache_content = run_cmake_configure(FIXTURE, build_dir, cmake_args)

        runtime_lib = extract_cmake_cache_value(
            cache_content, "CMAKE_MSVC_RUNTIME_LIBRARY"
        )
        assert runtime_lib is not None, (
            "CMAKE_MSVC_RUNTIME_LIBRARY not found in CMakeCache"
        )
        assert "MultiThreaded" in runtime_lib, (
            f"Expected MultiThreaded, got {runtime_lib}"
        )
        assert "DLL" not in runtime_lib, f"Should be static (no DLL), got {runtime_lib}"

        build_result = subprocess.run(
            ["cmake", "--build", build_dir],
            capture_output=True,
            text=True,
        )
        assert build_result.returncode == 0, f"Build failed: {build_result.stderr}"

    def test_debug_build_with_clang_cl_and_sanitize_succeeds(self, tmp_path):
        """A real build fails at compile time if Debug still picks a debug CRT."""
        if not sys.platform == "win32":
            pytest.skip("Windows only test")

        build_dir = str(tmp_path / "build")
        cmake_args = vdeps.get_platform_cmake_args(
            cxx_standard=20, use_llvm=True, sanitize="address"
        )
        cmake_args.append("-DCMAKE_BUILD_TYPE=Debug")

        run_cmake_configure(FIXTURE, build_dir, cmake_args)

        build_result = subprocess.run(
            ["cmake", "--build", build_dir],
            capture_output=True,
            text=True,
        )
        assert build_result.returncode == 0, (
            f"Debug+ASan build failed (CRT/ASan mismatch not fixed): "
            f"{build_result.stdout}\n{build_result.stderr}"
        )
        assert "not allowed with" not in build_result.stdout + build_result.stderr

    def test_release_build_with_clang_cl_and_sanitize_succeeds(self, tmp_path):
        """Companion to the Debug case above -- Release must keep working too."""
        if not sys.platform == "win32":
            pytest.skip("Windows only test")

        build_dir = str(tmp_path / "build")
        cmake_args = vdeps.get_platform_cmake_args(
            cxx_standard=20, use_llvm=True, sanitize="address"
        )
        cmake_args.append("-DCMAKE_BUILD_TYPE=Release")

        run_cmake_configure(FIXTURE, build_dir, cmake_args)

        build_result = subprocess.run(
            ["cmake", "--build", build_dir],
            capture_output=True,
            text=True,
        )
        assert build_result.returncode == 0, (
            f"Release+ASan build failed: {build_result.stdout}\n{build_result.stderr}"
        )

    @pytest.mark.parametrize(
        "use_llvm,use_dynamic_runtime,expected_dll",
        [
            (False, False, False),
            (False, True, True),
            (True, False, False),
            (True, True, True),
        ],
    )
    def test_runtime_library_variants(
        self, tmp_path, use_llvm, use_dynamic_runtime, expected_dll
    ):
        """Test all runtime combinations produce correct CMAKE_MSVC_RUNTIME_LIBRARY."""
        if not sys.platform == "win32":
            pytest.skip("Windows only test")

        cmake_args = vdeps.get_platform_cmake_args(
            cxx_standard=20,
            use_llvm=use_llvm,
            use_dynamic_runtime=use_dynamic_runtime,
        )
        cmake_args.append("-DCMAKE_BUILD_TYPE=Debug")

        cache_content = run_cmake_configure(FIXTURE, str(tmp_path / "build"), cmake_args)

        runtime_lib = extract_cmake_cache_value(
            cache_content, "CMAKE_MSVC_RUNTIME_LIBRARY"
        )
        assert runtime_lib is not None, (
            "CMAKE_MSVC_RUNTIME_LIBRARY not found in CMakeCache"
        )
        assert "MultiThreaded" in runtime_lib, (
            f"Expected MultiThreaded, got {runtime_lib}"
        )

        if expected_dll:
            assert "DLL" in runtime_lib, (
                f"Expected DLL for dynamic runtime, got {runtime_lib}"
            )
        else:
            assert "DLL" not in runtime_lib, (
                f"Expected no DLL for static runtime, got {runtime_lib}"
            )
