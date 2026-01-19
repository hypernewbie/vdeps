import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


class TestPlatformFiltering:
    """Test the filter_platform_items() function with various syntax patterns."""

    def test_plain_strings_pass_through(self):
        """Test that strings without platform prefix are always included."""
        items = ["-DFOO=ON", "-DBAR=OFF", "some_lib"]
        result = vdeps.filter_platform_items(items)
        assert result == items

    def test_platform_positive_match(self):
        """Test that items with matching platform prefix are included."""
        vdeps.PLATFORM_TAG = "win"
        items = ["win:-DWIN_FEATURE=ON", "linux:-DLINUX_FEATURE=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert "-DWIN_FEATURE=ON" in result
        assert "-DLINUX_FEATURE=ON" not in result
        assert "-DCOMMON=ON" in result

    def test_platform_positive_nomatch(self):
        """Test that items with non-matching platform prefix are excluded."""
        vdeps.PLATFORM_TAG = "linux"
        items = ["win:-DWIN_FEATURE=ON", "mac:-DMAC_FEATURE=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert "-DWIN_FEATURE=ON" not in result
        assert "-DMAC_FEATURE=ON" not in result
        assert "-DCOMMON=ON" in result

    def test_platform_negation_match(self):
        """Test that items with negated platform prefix work correctly."""
        vdeps.PLATFORM_TAG = "win"
        items = ["!win:-DNOT_WINDOWS=ON", "!linux:-DNOT_LINUX=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert "-DNOT_WINDOWS=ON" not in result
        assert "-DNOT_LINUX=ON" in result
        assert "-DCOMMON=ON" in result

    def test_multiple_platforms(self):
        """Test that comma-separated platform lists work correctly."""
        vdeps.PLATFORM_TAG = "linux"
        items = ["win,linux:-DMULTI_PLATFORM=ON", "win,mac:-DOTHER=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert "-DMULTI_PLATFORM=ON" in result
        assert "-DOTHER=ON" not in result
        assert "-DCOMMON=ON" in result

    def test_multiple_platforms_negation(self):
        """Test that comma-separated platform lists with negation work."""
        vdeps.PLATFORM_TAG = "mac"
        items = ["!win,linux:-DEXCLUDE_WIN_LINUX=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert "-DEXCLUDE_WIN_LINUX=ON" in result
        assert "-DCOMMON=ON" in result

    def test_all_platform_tags(self):
        """Test filtering with all three platform tags."""
        vdeps.PLATFORM_TAG = "mac"
        items = ["win:-DWIN=ON", "linux:-DLINUX=ON", "mac:-DMAC=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert result == ["-DMAC=ON", "-DCOMMON=ON"]


class TestCxxStandard:
    """Test C++ standard configuration."""

    def test_default_cxx_standard(self):
        """Test that dependencies default to C++20 when not specified."""
        dep = vdeps.Dependency(name="test_dep", rel_path="test/path", cmake_options=[])
        assert dep.cxx_standard == 20

    def test_custom_cxx_standard(self):
        """Test that custom C++ standard can be set."""
        dep = vdeps.Dependency(
            name="test_dep", rel_path="test/path", cmake_options=[], cxx_standard=17
        )
        assert dep.cxx_standard == 17

    def test_cmake_args_use_standard(self):
        """Test that get_platform_cmake_args() uses the specified standard."""
        vdeps.IS_WINDOWS = False
        vdeps.IS_MACOS = False
        vdeps.PLATFORM_TAG = "linux"
        args = vdeps.get_platform_cmake_args(cxx_standard=17)
        assert "-DCMAKE_CXX_STANDARD=17" in args
        assert "-DCMAKE_CXX_STANDARD=20" not in args

    def test_cmake_args_default_standard(self):
        """Test that get_platform_cmake_args() defaults to C++20."""
        vdeps.IS_WINDOWS = False
        vdeps.IS_MACOS = False
        vdeps.PLATFORM_TAG = "linux"
        args = vdeps.get_platform_cmake_args()
        assert "-DCMAKE_CXX_STANDARD=20" in args


class TestTempDir:
    """Test temp_dir build directory redirection."""

    def test_temp_dir_toml_parsing(self, tmp_path):
        """Test that temp_dir field can be parsed from TOML."""
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib

        toml_content = """
temp_dir = "build_artifacts"

[[dependency]]
name = "test_dep"
rel_path = "test/path"
cmake_options = []
"""
        toml_file = tmp_path / "vdeps.toml"
        toml_file.write_text(toml_content)

        with open(toml_file, "rb") as f:
            toml_data = tomllib.load(f)

        assert toml_data.get("temp_dir") == "build_artifacts"

    def test_build_dir_without_temp_dir(self):
        """Test that build directory is inside dependency folder without temp_dir."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = None
        dep_dir = "/path/to/deps/dep"
        dep_name = "dep"

        if temp_dir:
            build_dir = os.path.join(
                os.path.dirname(dep_dir), temp_dir, f"{dep_name}_{config['name']}"
            )
        else:
            build_dir = os.path.join(dep_dir, f"build_{config['name']}")

        expected = os.path.normpath("/path/to/deps/dep/build_debug")
        assert os.path.normpath(build_dir) == expected

    def test_build_dir_with_temp_dir(self):
        """Test that build directory is redirected to temp_dir when specified."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = "build_artifacts"
        dep_dir = "/path/to/deps/dep"
        dep_name = "dep"
        root_dir = "/path/to"

        if temp_dir:
            build_dir = os.path.join(root_dir, temp_dir, f"{dep_name}_{config['name']}")
        else:
            build_dir = os.path.join(dep_dir, f"build_{config['name']}")

        expected = os.path.normpath("/path/to/build_artifacts/dep_debug")
        assert os.path.normpath(build_dir) == expected


class TestIntegration:
    """Integration tests combining new features."""

    def test_platform_filtered_cmake_options(self, tmp_path):
        """Test that platform-specific CMake options are correctly filtered."""
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib

        toml_content = """
[[dependency]]
name = "test_dep"
rel_path = "test/path"
cmake_options = [
    "-DCOMMON=ON",
    "win:-DWIN_ONLY=ON",
    "linux:-DLINUX_ONLY=ON",
    "!win:-DNOT_WINDOWS=ON"
]
"""
        toml_file = tmp_path / "vdeps.toml"
        toml_file.write_text(toml_content)

        # Test on Linux
        with open(toml_file, "rb") as f:
            toml_data = tomllib.load(f)

        vdeps.PLATFORM_TAG = "linux"
        vdeps.IS_WINDOWS = False
        vdeps.IS_MACOS = False

        dep_data = toml_data["dependency"][0]
        dep = vdeps.Dependency(**dep_data)
        dep.cmake_options = vdeps.filter_platform_items(dep.cmake_options)

        assert "-DCOMMON=ON" in dep.cmake_options
        assert "-DWIN_ONLY=ON" not in dep.cmake_options
        assert "-DLINUX_ONLY=ON" in dep.cmake_options
        assert "-DNOT_WINDOWS=ON" in dep.cmake_options

    def test_backward_compatibility_no_new_fields(self):
        """Test that dependencies without new fields work as before."""
        dep = vdeps.Dependency(
            name="test_dep",
            rel_path="test/path",
            cmake_options=["-DOPTION=ON"],
            libs=["test_lib"],
            executables=["test_exe"],
        )

        assert dep.cxx_standard == 20  # Default
        assert dep.cmake_options == ["-DOPTION=ON"]
        assert dep.libs == ["test_lib"]
        assert dep.executables == ["test_exe"]
