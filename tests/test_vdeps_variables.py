import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add project root to path so we can import vdeps
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

def test_variable_interpolation(mock_subproc, mock_shutil):
    """
    Test that ${ROOT_DIR} is correctly interpolated in cmake_options.
    """
    
    # Mock TOML data with ${ROOT_DIR} usage
    mock_toml_data = {
        "dependency": [
            {
                "name": "var_dep",
                "rel_path": "deps/var_dep",
                "cmake_options": [
                    "-DTEST_ABS_PATH=${ROOT_DIR}/external/libs",
                    "-DTEST_NORMAL_OPT=ON"
                ],
                "libs": [],
                "executables": [],
                "build_by_default": True
            }
        ]
    }

    # Mock glob to return nothing so we don't error on copy
    def mock_glob(pattern, recursive=False):
        return []

    # Mock open/tomllib.load to return our data
    # We also need to mock os.path.exists to pass validations
    
    # Determine what we expect ROOT_DIR to be based on how we mock __file__
    mock_script_path = os.path.join(FIXTURES_DIR, "mock_vdeps.py")
    expected_root_dir = FIXTURES_DIR.replace(os.sep, "/")
    expected_arg = f"-DTEST_ABS_PATH={expected_root_dir}/external/libs"

    with (patch('sys.platform', 'linux'), 
          patch('vdeps.IS_WINDOWS', False), 
          patch('vdeps.IS_MACOS', False), 
          patch('vdeps.PLATFORM_TAG', 'linux'), 
          patch('glob.glob', side_effect=mock_glob), 
          patch('os.path.exists', return_value=True), 
          patch('builtins.open', MagicMock()), 
          patch('tomllib.load', return_value=mock_toml_data)):
        
        # Mock __file__
        original_file = vdeps.__file__
        vdeps.__file__ = mock_script_path
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify CMake Calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0] and '-S' in c[0][0]]
    assert len(cmake_calls) == 2, "CMake configure should be called twice (Debug and Release)"
    
    args = cmake_calls[0][0][0]
    
    # Check if interpolation happened
    found_interpolated = False
    for arg in args:
        if arg.startswith("-DTEST_ABS_PATH="):
            # Verify variable was interpolated AND colon was preserved
            assert arg == expected_arg
            found_interpolated = True
            
    assert found_interpolated, f"Did not find expected interpolated argument: {expected_arg}"
    assert "-DTEST_NORMAL_OPT=ON" in args

def test_variable_interpolation_with_platform_prefix(mock_subproc, mock_shutil):
    """
    Test that ${ROOT_DIR} interpolation works with platform-prefixed cmake_options.
    """
    # Mock TOML data with ${ROOT_DIR} usage in platform-specific options
    mock_toml_data = {
        "dependency": [
            {
                "name": "platform_dep",
                "rel_path": "deps/platform_dep",
                "cmake_options": [
                    "linux:-DLINUX_PATH=${ROOT_DIR}/linux_libs",
                    "win:-DWIN_PATH=${ROOT_DIR}/win_libs",
                    "-DCOMMON=${ROOT_DIR}/common",
                ],
                "libs": [],
                "executables": [],
                "build_by_default": True
            }
        ]
    }

    # Mock glob to return nothing so we don't error on copy
    def mock_glob(pattern, recursive=False):
        return []

    # Determine what we expect ROOT_DIR to be based on how we mock __file__
    mock_script_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures')), "mock_vdeps.py")
    expected_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures')).replace(os.sep, "/")
    expected_linux_arg = f"-DLINUX_PATH={expected_root_dir}/linux_libs"
    expected_common_arg = f"-DCOMMON={expected_root_dir}/common"

    with (patch('sys.platform', 'linux'), 
          patch('vdeps.IS_WINDOWS', False), 
          patch('vdeps.IS_MACOS', False), 
          patch('vdeps.PLATFORM_TAG', 'linux'), 
          patch('glob.glob', side_effect=mock_glob), 
          patch('os.path.exists', return_value=True), 
          patch('builtins.open', MagicMock()), 
          patch('tomllib.load', return_value=mock_toml_data)):
        
        # Mock __file__
        original_file = vdeps.__file__
        vdeps.__file__ = mock_script_path
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify CMake Calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0] and '-S' in c[0][0]]
    assert len(cmake_calls) == 2, "CMake configure should be called twice (Debug and Release)"
    
    args = cmake_calls[0][0][0]
    
    # Check that linux-prefixed interpolated option appears
    found_linux = False
    found_common = False
    for arg in args:
        if arg.startswith("-DLINUX_PATH="):
            assert arg == expected_linux_arg
            found_linux = True
        if arg.startswith("-DCOMMON="):
            assert arg == expected_common_arg
            found_common = True
    
    assert found_linux, f"Did not find expected linux interpolated argument: {expected_linux_arg}"
    assert found_common, f"Did not find expected common interpolated argument: {expected_common_arg}"
    # Ensure win-prefixed option does NOT appear (platform mismatch)
    assert not any(arg.startswith("-DWIN_PATH=") for arg in args), "Win-prefixed option should not appear on linux platform"
