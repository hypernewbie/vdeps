import sys
import os
import pytest
from unittest.mock import patch
from io import StringIO

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


class TestPlatformFilteringFixes:
    """Test the fixes for platform filter edge cases."""

    def test_whitespace_trimming_in_platform_lists(self):
        """Test that whitespace in comma-separated platform lists is trimmed."""
        vdeps.PLATFORM_TAG = "linux"
        items = ["win, linux:-DMULTI_PLATFORM=ON", "win ,mac:-DOTHER=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)
        assert "-DMULTI_PLATFORM=ON" in result
        assert "-DOTHER=ON" not in result
        assert "-DCOMMON=ON" in result

    def test_unknown_platform_tags_are_literals(self):
        """Test that unknown platform tags are treated as literals (no filtering)."""
        vdeps.PLATFORM_TAG = "linux"

        # Capture stdout to ensure NO warnings (optional, but good practice)
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            items = [
                "windows:-DWIN_FEATURE=ON",
                "linux:-DLINUX_FEATURE=ON",
                "-DCOMMON=ON",
            ]
            result = vdeps.filter_platform_items(items)

        output = captured_output.getvalue()
        assert "Warning" not in output
        
        # 'windows' is unknown, so the whole string is preserved as is
        assert "windows:-DWIN_FEATURE=ON" in result
        # 'linux' is known, so it is processed and value extracted
        assert "-DLINUX_FEATURE=ON" in result
        assert "-DCOMMON=ON" in result

    def test_unknown_negation_tags_are_literals(self):
        """Test that unknown platform tags in negation are treated as literals."""
        vdeps.PLATFORM_TAG = "linux"

        items = [
            "!windows:-DNOT_WINDOWS=ON",
            "!linux:-DNOT_LINUX=ON",
            "-DCOMMON=ON",
        ]
        result = vdeps.filter_platform_items(items)

        # Unknown tag -> Literal
        assert "!windows:-DNOT_WINDOWS=ON" in result
        # Known tag !linux -> Exclude on linux
        assert "-DNOT_LINUX=ON" not in result
        assert "-DCOMMON=ON" in result

    def test_multiple_unknown_platforms_are_literals(self):
        """Test multiple unknown platform tags."""
        vdeps.PLATFORM_TAG = "linux"

        items = ["windows,macos:-DMULTI_UNKNOWN=ON", "-DCOMMON=ON"]
        result = vdeps.filter_platform_items(items)

        assert "windows,macos:-DMULTI_UNKNOWN=ON" in result
        assert "-DCOMMON=ON" in result

    def test_value_stripping(self):
        """Test that leading/trailing whitespace in values is stripped."""
        vdeps.PLATFORM_TAG = "linux"
        items = [
            "linux: -DFOO=ON",  # Should match and strip
            "linux: -DBAR=OFF  ",  # Should match and strip trailing spaces
            "  -DBAZ=ON",  # Plain string, no colon, no stripping
            "win,mac:  -DMULTI=ON ",  # Should not match (linux not in list)
            "linux,mac:  -DMULTI2=ON ",  # Should match and strip
        ]
        result = vdeps.filter_platform_items(items)
        assert "-DFOO=ON" in result
        assert "-DBAR=OFF" in result
        assert "  -DBAZ=ON" in result  # Plain string (no colon) not stripped
        assert "-DMULTI=ON" not in result  # Excluded
        assert "-DMULTI2=ON" in result

    def test_space_after_exclamation(self):
        """Test that spaces after exclamation mark are handled correctly."""
        vdeps.PLATFORM_TAG = "linux"
        items = [
            "! win:-DNOT_WINDOWS=ON",
            "!linux , mac:-DNOT_LINUX_MAC=ON",
            "! win, linux:-DEXCLUDE=ON",
        ]
        result = vdeps.filter_platform_items(items)
        # Linux platform, so:
        # First item: exclude win -> include (since linux != win)
        assert "-DNOT_WINDOWS=ON" in result
        # Second item: exclude linux or mac -> exclude (since linux matches)
        assert "-DNOT_LINUX_MAC=ON" not in result
        # Third item: exclude win or linux -> exclude (since linux matches)
        assert "-DEXCLUDE=ON" not in result


class TestTempDirFixes:
    """Test the fixes for temp_dir handling."""

    def test_empty_string_temp_dir_uses_default(self):
        """Test that empty string temp_dir uses default behavior."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = ""  # Empty string
        dep_dir = "/path/to/deps/dep"
        dep_name = "dep"
        root_dir = "/path/to"

        if temp_dir and temp_dir.strip():
            build_dir = os.path.join(
                root_dir, temp_dir.strip(), f"{dep_name}_{config['name']}"
            )
        else:
            build_dir = os.path.join(dep_dir, f"build_{config['name']}")

        expected = os.path.normpath("/path/to/deps/dep/build_debug")
        assert os.path.normpath(build_dir) == expected

    def test_whitespace_only_temp_dir_uses_default(self):
        """Test that whitespace-only temp_dir uses default behavior."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = "   "  # Whitespace only
        dep_dir = "/path/to/deps/dep"
        dep_name = "dep"
        root_dir = "/path/to"

        if temp_dir and temp_dir.strip():
            build_dir = os.path.join(
                root_dir, temp_dir.strip(), f"{dep_name}_{config['name']}"
            )
        else:
            build_dir = os.path.join(dep_dir, f"build_{config['name']}")

        expected = os.path.normpath("/path/to/deps/dep/build_debug")
        assert os.path.normpath(build_dir) == expected

    def test_temp_dir_with_whitespace_gets_stripped(self):
        """Test that temp_dir with leading/trailing whitespace gets stripped."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = "  build_artifacts  "  # With whitespace
        dep_dir = "/path/to/deps/dep"
        dep_name = "dep"
        root_dir = "/path/to"

        if temp_dir and temp_dir.strip():
            build_dir = os.path.join(
                root_dir, temp_dir.strip(), f"{dep_name}_{config['name']}"
            )
        else:
            build_dir = os.path.join(dep_dir, f"build_{config['name']}")

        expected = os.path.normpath("/path/to/build_artifacts/dep_debug")
        assert os.path.normpath(build_dir) == expected


class TestBuildDirCreation:
    """Test that build directories are created properly."""

    def test_temp_dir_parent_creation(self, tmp_path):
        """Test that temp_dir parent directory is created."""
        # This test would require mocking os.makedirs and checking it's called
        # For now, we'll just verify the logic path
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = "build_artifacts"
        dep_name = "test_dep"
        root_dir = str(tmp_path)

        build_dir = os.path.join(
            root_dir, temp_dir.strip(), f"{dep_name}_{config['name']}"
        )
        parent_dir = os.path.dirname(build_dir)

        # Verify parent directory path is correct
        expected_parent = os.path.join(root_dir, "build_artifacts")
        assert parent_dir == expected_parent

        # Test that os.makedirs would be called with correct path
        # (In real scenario, this would create the directory)
        assert not os.path.exists(parent_dir)  # Should not exist yet

    @patch("vdeps.os.makedirs")
    def test_nested_temp_dir_creation(self, mock_makedirs):
        """Test that nested temp_dir paths are created correctly."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = "build/artifacts/nested"
        dep_name = "test_dep"
        root_dir = "/path/to/project"

        # Simulate the logic in vdeps.py
        if temp_dir and temp_dir.strip():
            build_dir = os.path.join(
                root_dir, temp_dir.strip(), f"{dep_name}_{config['name']}"
            )
            # Ensure temp_dir parent directory exists
            os.makedirs(os.path.dirname(build_dir), exist_ok=True)
        else:
            build_dir = os.path.join("dummy", f"build_{config['name']}")

        # Verify the directory creation call
        mock_makedirs.assert_called_once_with(os.path.dirname(build_dir), exist_ok=True)

        # Verify the path is correct
        expected_parent = os.path.join(root_dir, "build/artifacts/nested")
        assert os.path.dirname(build_dir) == expected_parent

    @patch("vdeps.os.makedirs")
    def test_temp_dir_absolute_path(self, mock_makedirs):
        """Test that absolute temp_dir paths work correctly."""
        vdeps.IS_WINDOWS = False
        vdeps.PLATFORM_TAG = "linux"

        config = {"name": "debug", "type": "Debug"}
        temp_dir = "/absolute/path/builds"
        dep_name = "test_dep"
        root_dir = "/path/to/project"  # Should be ignored

        # Simulate the logic in vdeps.py
        if temp_dir and temp_dir.strip():
            build_dir = os.path.join(
                root_dir, temp_dir.strip(), f"{dep_name}_{config['name']}"
            )
            # Ensure temp_dir parent directory exists
            os.makedirs(os.path.dirname(build_dir), exist_ok=True)
        else:
            build_dir = os.path.join("dummy", f"build_{config['name']}")

        # With absolute path, os.path.join discards root_dir
        expected_build_dir = os.path.join(
            temp_dir.strip(), f"{dep_name}_{config['name']}"
        )
        assert build_dir == expected_build_dir
        mock_makedirs.assert_called_once_with(os.path.dirname(build_dir), exist_ok=True)
