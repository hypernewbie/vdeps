import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import vdeps

@pytest.fixture
def mock_subproc():
    with patch("subprocess.run") as mock:
        mock.return_value.returncode = 0
        yield mock

@pytest.fixture
def mock_shutil():
    with patch("shutil.copy2") as mock:
        yield mock

def test_install_target_variables(mock_subproc, mock_shutil):
    """
    Test that ${PLATFORM_SUBDIR}, ${CONFIG_NAME}, and ${ROOT_DIR} 
    are correctly interpolated in install target paths.
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "InterpolatedInstall",
                "rel_path": "deps/interp",
                "cmake_options": [],
                "build": False, # Skip build to focus on install logic
                "install": [
                    {
                        "pattern": "*.lib", 
                        "target": "libs/${PLATFORM_SUBDIR}_${CONFIG_NAME}"
                    },
                    {
                        "pattern": "*.data",
                        "target": "${ROOT_DIR}/data/${CONFIG_NAME}"
                    }
                ]
            }
        ]
    }

    # Mock glob to return fake files
    def mock_glob_side_effect(pattern, recursive=False):
        if "*.lib" in pattern:
            return ["/path/to/deps/interp/build/libfoo.lib"]
        if "*.data" in pattern:
            return ["/path/to/deps/interp/build/assets.data"]
        return []

    # Mock context
    # We'll simulate Windows LLVM to get interesting PLATFORM_SUBDIR="win_llvm"
    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', '--llvm', 'InterpolatedInstall']),
        patch('glob.glob', side_effect=mock_glob_side_effect),
        patch('os.makedirs'),
        patch('sys.platform', 'win32'),
        patch('vdeps.IS_WINDOWS', True),
        patch('vdeps.PLATFORM_TAG', 'win'),
        patch('shutil.which', return_value="/usr/bin/dummy")
    ):
        vdeps.main()

    # We expect 2 configs: debug and release
    # For Windows LLVM:
    #   PLATFORM_SUBDIR = "win_llvm"
    #   CONFIG_NAME = "debug" / "release"
    
    # Expected targets:
    #   libs/win_llvm_debug
    #   libs/win_llvm_release
    
    #   ${ROOT_DIR}/data/debug
    #   ${ROOT_DIR}/data/release

    copy_calls = mock_shutil.call_args_list
    destinations = [call[0][1] for call in copy_calls]

    # Verify win_llvm_debug exists in some path. Use double backslashes for Windows paths in regex/strings.
    assert any("libs\\win_llvm_debug" in d or "libs/win_llvm_debug" in d for d in destinations)
    assert any("libs\\win_llvm_release" in d or "libs/win_llvm_release" in d for d in destinations)

    # Verify data/debug and data/release
    assert any("data\\debug" in d or "data/debug" in d for d in destinations)
    assert any("data\\release" in d or "data/release" in d for d in destinations)

def test_install_target_variables_standard_linux(mock_subproc, mock_shutil):
    """
    Test variables on standard Linux (no llvm flag).
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "LinuxInstall",
                "rel_path": "deps/linux",
                "cmake_options": [],
                "build": False,
                "install": [
                    {
                        "pattern": "*.a", 
                        "target": "custom/${PLATFORM_SUBDIR}/${CONFIG_NAME}"
                    }
                ]
            }
        ]
    }

    def mock_glob_side_effect(pattern, recursive=False):
        if "*.a" in pattern:
            return ["/path/to/deps/linux/libfoo.a"]
        return []

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'LinuxInstall']),
        patch('glob.glob', side_effect=mock_glob_side_effect),
        patch('os.makedirs'),
        patch('sys.platform', 'linux'),
        patch('vdeps.IS_WINDOWS', False),
        patch('vdeps.PLATFORM_TAG', 'linux')
    ):
        vdeps.main()

    copy_calls = mock_shutil.call_args_list
    destinations = [call[0][1] for call in copy_calls]

    # Expect: custom/linux/debug and custom/linux/release
    assert any("custom\\linux\\debug" in d or "custom/linux/debug" in d for d in destinations)
    assert any("custom\\linux\\release" in d or "custom/linux/release" in d for d in destinations)
