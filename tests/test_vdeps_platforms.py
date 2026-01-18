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

def test_macos_build(mock_subproc, mock_shutil):
    """
    Test behaviour when running on macOS:
    - Should use Ninja generator
    - Should use libc++ without -lc++abi (macOS includes it)
    - Should look for .a libraries and .dylib files
    - Should look for executables without extension
    """
    def mock_glob_function(pattern, recursive=False):
        # Return macOS-specific artifacts
        if 'fake_lib' in pattern and 'build_debug' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_lib' in pattern and 'build_release' in pattern:
            return ['/path/to/fake_lib/build_release/libfake_lib.a']
        elif 'fake_tool' in pattern and 'build_debug' in pattern:
            return ['/path/to/fake_tool/build_debug/fake_tool']
        elif 'fake_tool' in pattern and 'build_release' in pattern:
            return ['/path/to/fake_tool/build_release/fake_tool']
        return []
    
    # Store original values
    orig_is_windows = vdeps.IS_WINDOWS
    orig_is_macos = vdeps.IS_MACOS
    orig_platform_tag = vdeps.PLATFORM_TAG
    orig_lib_ext = vdeps.LIB_EXT
    
    # Set macOS values
    vdeps.IS_WINDOWS = False
    vdeps.IS_MACOS = True
    vdeps.PLATFORM_TAG = 'mac'
    vdeps.LIB_EXT = '.a'
    
    # Mock __file__ to point to fixtures
    original_file = vdeps.__file__
    vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
    
    try:
        with patch('sys.platform', 'darwin'), \
             patch('glob.glob', side_effect=mock_glob_function):
            vdeps.main()
    finally:
        vdeps.__file__ = original_file
        # Restore original values
        vdeps.IS_WINDOWS = orig_is_windows
        vdeps.IS_MACOS = orig_is_macos
        vdeps.PLATFORM_TAG = orig_platform_tag
        vdeps.LIB_EXT = orig_lib_ext

    # Verify CMake Calls include macOS-specific flags
    cmake_calls = [c for c in mock_subproc.call_args_list]
    
    # Find first cmake configure call
    configure_calls = []
    for call in cmake_calls:
        args_list = call[0][0] if call[0] else []
        if isinstance(args_list, list) and 'cmake' in args_list and '-S' in args_list:
            configure_calls.append(call)
    
    assert len(configure_calls) >= 1, f"Expected cmake configure calls, but got none. All calls: {cmake_calls}"
    
    args = configure_calls[0][0][0]
    assert '-G' in args and 'Ninja' in args, "Should use Ninja on macOS"
    assert '-DCMAKE_CXX_COMPILER=clang++' in args, "Should use Clang on macOS"
    
    # Verify linker flags have no -lc++abi on macOS
    ld_flags_line = [a for a in args if 'CMAKE_EXE_LINKER_FLAGS' in a]
    if ld_flags_line:
        # macOS shouldn't have -lc++abi
        assert '-lc++abi' not in ld_flags_line[0], "macOS should NOT have -lc++abi"
        assert '-stdlib=libc++' in ld_flags_line[0], "macOS should have -stdlib=libc++"
    
    # Verify copy was called (mock_shutil should have been called)
    assert len(mock_shutil.call_args_list) > 0, "Should have attempted to copy artefacts"

