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

def test_windows_env_vars(mock_subproc, mock_shutil):
    """
    Test that environment variables (LIB, CMAKE_LIBRARY_PATH) are correctly set on Windows.
    """
    with patch('sys.platform', 'win32'), \
         patch('glob.glob', return_value=[]), \
         patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'win'):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        # Expected lib dir based on fixture path
        expected_lib_root = os.path.join(FIXTURES_DIR, 'lib')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify calls
    # We look for the call corresponding to building a dependency (cmake --build or cmake -S)
    # vdeps.toml in fixtures has 'fake_lib' 
    
    # Filter for cmake calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0]]
    assert len(cmake_calls) > 0, "Should have called cmake"
    
    for call_args in cmake_calls:
        args, kwargs = call_args
        env = kwargs.get('env')
        assert env is not None, "Environment should be passed to cmake"
        
        # Check LIB
        lib_env = env.get('LIB', '')
        # We expect paths like .../fixtures/lib/win_debug or .../fixtures/lib/win_release
        assert expected_lib_root in lib_env, f"LIB env var should contain library path. Got: {lib_env}"
        
        # Check CMAKE_LIBRARY_PATH
        cmake_lib_path = env.get('CMAKE_LIBRARY_PATH', '')
        assert expected_lib_root in cmake_lib_path


def test_library_paths_injection(mock_subproc, mock_shutil):
    """
    Test that 'library_paths' from TOML are correctly added to environment variables.
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "test_lib_paths",
                "rel_path": "fake_lib",
                "cmake_options": [],
                "library_paths": [os.path.join("external", "libs"), "/opt/local/lib"]
            }
        ]
    }

    # We need to mock open() to avoid FileNotFoundError when vdeps tries to open vdeps.toml
    # And we need to mock tomllib.load to return our data
    # And os.path.exists to say vdeps.toml exists
    
    with patch('sys.platform', 'win32'), \
         patch('glob.glob', return_value=[]), \
         patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
                      patch('vdeps.tomllib.load', return_value=mock_toml_data), \
                      patch('builtins.open', new_callable=MagicMock), \
                      patch('os.path.exists') as mock_exists, \
                      patch('os.makedirs'):
        # Configure path existence
        def side_effect(path):
            # Allow vdeps.toml check
            if 'vdeps.toml' in path: return True
            # Allow dependency dir check (we point to fixture)
            if 'fake_lib' in path: return True
            return False
        mock_exists.side_effect = side_effect
        
        original_file = vdeps.__file__
        # Point to fixtures dir so it resolves 'fake_lib' correctly (relative to root)
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0]]
    assert len(cmake_calls) > 0
    
    # Check the first build call
    args, kwargs = cmake_calls[0]
    env = kwargs.get('env')
    lib_env = env.get('LIB', '')
    
    # 1. Check relative path resolution (relative to fixtures dir)
    expected_resolved = os.path.join(FIXTURES_DIR, "external", "libs")
    assert expected_resolved in lib_env, f"Should resolve relative library_paths. Got: {lib_env}"
    
    # 2. Check absolute path preservation
    assert "/opt/local/lib" in lib_env, "Should preserve absolute library_paths"
    
    # 3. Check that it uses correct separator (;)
    assert ';' in lib_env



def test_linux_env_vars(mock_subproc, mock_shutil):
    """
    Test that environment variables (LIBRARY_PATH, CMAKE_LIBRARY_PATH) are correctly set on Linux.
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
    
    for call_args in cmake_calls:
        args, kwargs = call_args
        env = kwargs.get('env')
        assert env is not None
        
        # Check LIBRARY_PATH (Linux specific)
        lib_path_env = env.get('LIBRARY_PATH', '')
        assert expected_lib_root in lib_path_env, f"LIBRARY_PATH should be set. Got: {lib_path_env}"
        
        # Check CMAKE_LIBRARY_PATH
        cmake_lib_path = env.get('CMAKE_LIBRARY_PATH', '')
        assert expected_lib_root in cmake_lib_path
