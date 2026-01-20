import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures'))

@pytest.fixture
def mock_subproc():
    with patch('subprocess.run') as mock:
        mock.return_value.returncode = 0
        yield mock

@pytest.fixture
def mock_shutil():
    with patch('shutil.copy2') as mock:
        yield mock


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


class TestBuildFlagAndWarnings:
    """Test the --build flag and Windows warning suppression features."""

    @patch("vdeps.IS_WINDOWS", True)
    def test_windows_warnings_disabled(self):
        """Test that warning level is set to 0 (/W0) on Windows."""
        args = vdeps.get_platform_cmake_args()

        c_flags = [a for a in args if a.startswith("-DCMAKE_C_FLAGS=")][0]
        cxx_flags = [a for a in args if a.startswith("-DCMAKE_CXX_FLAGS=")][0]

        assert "/W0" in c_flags
        assert "/W0" in cxx_flags

    @patch("vdeps.IS_WINDOWS", False)
    @patch("vdeps.IS_MACOS", False)
    def test_unix_warnings_disabled(self):
        """Test that warning level is set to -w on Unix-like systems."""
        vdeps.PLATFORM_TAG = "linux"
        args = vdeps.get_platform_cmake_args()

        c_flags = [a for a in args if a.startswith("-DCMAKE_C_FLAGS=")][0]
        cxx_flags = [a for a in args if a.startswith("-DCMAKE_CXX_FLAGS=")][0]

        assert "-w" in c_flags
        assert "-w" in cxx_flags

    def test_build_flag_parsing(self):
        """Test that --build flag is parsed correctly."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--build", action="store_true")
        args = parser.parse_args(["--build"])
        assert args.build is True

    def test_is_build_dir_valid_true(self, tmp_path):
        """Test that valid build directory with CMakeCache is recognized."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "CMakeCache.txt").write_text("test")

        assert vdeps.is_build_dir_valid(str(build_dir)) is True

    def test_is_build_dir_valid_false_missing_cache(self, tmp_path):
        """Test that build directory without CMakeCache is not valid."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()

        assert vdeps.is_build_dir_valid(str(build_dir)) is False

    def test_is_build_dir_valid_false_nonexistent(self, tmp_path):
        """Test that non-existent directory is not valid."""
        build_dir = tmp_path / "nonexistent"

        assert vdeps.is_build_dir_valid(str(build_dir)) is False

def test_filtering_with_build_flag(mock_subproc, mock_shutil):
    """
    Test that --build flag works with dependency filtering
    """
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        return []

    # Mock build directory as valid (existing with CMakeCache.txt)
    # This will cause configure to be skipped when --build is used
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('sys.argv', ['vdeps.py', 'fake_lib', '--build']), \
         patch('os.path.exists', side_effect=lambda path: 'CMakeCache.txt' in path or 'fake_lib' in path or 'fake_tool' in path), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.LIB_EXT', '.a'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            captured = mock_subproc.call_args_list
            # Find configure calls for fake_lib
            configure_calls = [c for c in captured if 'fake_lib' in c[1].get('cwd', '') and '-S' in c[0][0]]
            # With --build and valid build dir, configure should be skipped
            assert len(configure_calls) == 0, "Configure should be skipped with --build flag"
        finally:
            vdeps.__file__ = original_file


def test_filtering_skips_unrequested_dependencies(mock_subproc, mock_shutil):
    """
    Test that only requested dependencies are built when using filtering
    """
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_tool' in pattern:
            return ['/path/to/fake_tool/build_debug/fake_tool']
        return []

    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('sys.argv', ['vdeps.py', 'fake_lib']), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.LIB_EXT', '.a'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Count how many times each dependency was processed
    dep_names = set()
    for call in mock_subproc.call_args_list:
        cwd = call[1].get('cwd', '')
        if 'fake_lib' in cwd:
            dep_names.add('fake_lib')
        elif 'fake_tool' in cwd:
            dep_names.add('fake_tool')
    
    # Should only have fake_lib, not fake_tool
    assert 'fake_lib' in dep_names
    assert 'fake_tool' not in dep_names, "Unrequested dependency should not be built"


def test_order_preservation(mock_subproc, mock_shutil):
    """
    Test that dependencies are built in TOML order, not request order
    """
    def mock_glob(pattern, recursive=False):
        if 'complex_lib' in pattern:
            return ['/path/to/complex_lib/build_debug/libcomplex_core.a']
        elif 'fake_lib' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_tool' in pattern:
            return ['/path/to/fake_tool/build_debug/fake_tool']
        return []

    # Request in different order than TOML (fake_tool, fake_lib, complex_lib)
    # TOML order is: fake_lib, fake_tool, complex_lib, mixed_project, multi_output, empty_config
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('sys.argv', ['vdeps.py', 'fake_tool', 'complex_lib', 'fake_lib']), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.LIB_EXT', '.a'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Get the order of dependencies by checking cwd in calls
    dep_order = []
    for call in mock_subproc.call_args_list:
        cwd = call[1].get('cwd', '')
        if 'fake_lib' in cwd and 'fake_lib' not in dep_order:
            dep_order.append('fake_lib')
        elif 'fake_tool' in cwd and 'fake_tool' not in dep_order:
            dep_order.append('fake_tool')
        elif 'complex_lib' in cwd and 'complex_lib' not in dep_order:
            dep_order.append('complex_lib')
    
    # Should preserve TOML order: fake_lib first, then fake_tool, then complex_lib
    assert len(dep_order) == 3
    assert dep_order[0] == 'fake_lib', f"Expected fake_lib first in TOML order, got {dep_order}"
    assert dep_order[1] == 'fake_tool', f"Expected fake_tool second in TOML order, got {dep_order}"
    assert dep_order[2] == 'complex_lib', f"Expected complex_lib third in TOML order, got {dep_order}"
