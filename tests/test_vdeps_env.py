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

def test_windows_linker_flags(mock_subproc, mock_shutil):
    """
    Test that on Windows, library paths are converted to /LIBPATH:"..." flags 
    and passed to CMake via -DCMAKE_EXE_LINKER_FLAGS and -DCMAKE_SHARED_LINKER_FLAGS.
    """
    with patch('sys.platform', 'win32'), \
         patch('glob.glob', return_value=[]), \
         patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'win'):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        expected_lib_root = os.path.join(FIXTURES_DIR, 'lib')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify calls
    # Filter for cmake calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0]]
    assert len(cmake_calls) > 0, "Should have called cmake"
    
    # Check the first configure call (fake_lib)
    args = cmake_calls[0][0][0]
    
    # Find linker flags arg
    # We now expect MERGED flags, so find any argument starting with -DCMAKE_EXE_LINKER_FLAGS=
    linker_flag_arg = next((a for a in args if '-DCMAKE_EXE_LINKER_FLAGS=' in a), None)
    assert linker_flag_arg is not None, "Should have CMAKE_EXE_LINKER_FLAGS"
    
    # Check content
    # Expected: /LIBPATH:".../fixtures/lib/win_debug" (for debug config)
    # The path should be quoted
    assert '/LIBPATH:' in linker_flag_arg
    assert expected_lib_root in linker_flag_arg
    
    # Ensure it's quoted correctly
    assert f'"{expected_lib_root}' in linker_flag_arg or f'\'{expected_lib_root}' in linker_flag_arg

def test_linux_linker_flags(mock_subproc, mock_shutil):
    """
    Test that on Linux, library paths are converted to -L"..." flags 
    and passed to CMake.
    """
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', return_value=[]), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'linux'):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        expected_lib_root = os.path.join(FIXTURES_DIR, 'lib')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0]]
    assert len(cmake_calls) > 0
    
    args = cmake_calls[0][0][0]
    linker_flag_arg = next((a for a in args if '-DCMAKE_EXE_LINKER_FLAGS=' in a), None)
    assert linker_flag_arg is not None
    
    # Expected: -L".../fixtures/lib/linux_debug"
    assert '-L' in linker_flag_arg
    assert expected_lib_root in linker_flag_arg

def test_library_paths_injection(mock_subproc, mock_shutil):
    """
    Test that 'extra_link_dirs' from TOML are correctly added to CMake linker flags.
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "test_lib_paths",
                "rel_path": "fake_lib",
                "cmake_options": [],
                "extra_link_dirs": [os.path.join("external", "libs"), "C:/opt/local/lib"]
            }
        ]
    }

    with patch('sys.platform', 'win32'), \
         patch('glob.glob', return_value=[]), \
         patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
         patch('vdeps.tomllib.load', return_value=mock_toml_data), \
         patch('builtins.open', new_callable=MagicMock), \
         patch('os.path.exists') as mock_exists, \
         patch('os.makedirs'):

        def side_effect(path):
            if 'vdeps.toml' in path: return True
            if 'fake_lib' in path: return True
            return False
        mock_exists.side_effect = side_effect
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0]]
    assert len(cmake_calls) > 0
    
    args = cmake_calls[0][0][0]
    linker_flag_arg = next((a for a in args if '-DCMAKE_EXE_LINKER_FLAGS=' in a), None)
    
    # 1. Check relative path resolution
    expected_resolved = os.path.join(FIXTURES_DIR, "external", "libs")
    assert expected_resolved in linker_flag_arg
    
    # 2. Check absolute path
    assert "C:/opt/local/lib" in linker_flag_arg

    # 3. Check format (Windows)
    assert f'/LIBPATH:"{expected_resolved}"' in linker_flag_arg
    assert '/LIBPATH:"C:/opt/local/lib"' in linker_flag_arg
