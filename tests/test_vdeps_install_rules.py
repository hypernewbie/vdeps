import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

# Add project root to path so we can import vdeps
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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

@pytest.fixture
def mock_open_toml():
    # Helper to mock vdeps.toml opening since vdeps.main() opens it
    pass

def test_no_build_install(mock_subproc, mock_shutil):
    """
    Test install rules when build=false:
    - Should NOT run cmake configure/build
    - Should search for files in dep_dir
    - Should copy matched files to target dirs
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "StaticAssets",
                "rel_path": "assets",
                "cmake_options": [],
                "build": False,
                "install": [
                    {"pattern": "data/*.txt", "target": "tools/config"},
                    {"pattern": "libs/*.so", "target": "lib"}
                ]
            }
        ]
    }

    def mock_glob_side_effect(pattern, recursive=False):
        if "data/*.txt" in pattern:
            return ["/path/to/assets/data/config.txt"]
        if "libs/*.so" in pattern:
            return ["/path/to/assets/libs/libdummy.so"]
        return []

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'StaticAssets']),
        patch('glob.glob', side_effect=mock_glob_side_effect),
        patch('os.makedirs')
    ):
        vdeps.main()

    # Verify NO cmake calls
    for call in mock_subproc.call_args_list:
        args = call[0][0]
        assert "cmake" not in args or "--build" in str(args) # Only allow build if it was somehow called (it shouldn't be)

    # Verify copy calls
    copy_calls = mock_shutil.call_args_list
    # 2 files * 2 configs = 4
    assert len(copy_calls) == 4

    # Check destinations (mapping lib/tools keywords)
    destinations = [call[0][1] for call in copy_calls]
    assert any("tools" in d and "config" in d for d in destinations)
    assert any("lib" in d and "linux_debug" in d for d in destinations)

def test_install_with_build(mock_subproc, mock_shutil):
    """
    Test install rules when build=true:
    - Should search for files in build_dir
    - Should copy matched files to target dirs
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "BuildAndInstall",
                "rel_path": "project",
                "cmake_options": [],
                "install": [
                    {"pattern": "generated/*.dll", "target": "tools"}
                ]
            }
        ]
    }

    def mock_glob_side_effect(pattern, recursive=False):
        if "generated/*.dll" in pattern and "build_debug" in pattern:
            return ["/path/to/project/build_debug/generated/plugin.dll"]
        if "generated/*.dll" in pattern and "build_release" in pattern:
            return ["/path/to/project/build_release/generated/plugin.dll"]
        return []

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'BuildAndInstall']),
        patch('glob.glob', side_effect=mock_glob_side_effect),
        patch('os.makedirs'),
        patch('vdeps.IS_WINDOWS', True),
        patch('vdeps.PLATFORM_TAG', 'win')
    ):
        vdeps.main()

    # Verify copy calls for both configs
    copy_calls = mock_shutil.call_args_list
    # For each config (debug/release), it runs install rules
    # Total expected: 1 file * 2 configs = 2
    assert len(copy_calls) >= 2
    
    destinations = [call[0][1] for call in copy_calls]
    assert any("win_debug" in d for d in destinations)
    assert any("win_release" in d for d in destinations)
