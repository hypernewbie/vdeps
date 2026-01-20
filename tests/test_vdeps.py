import sys
import os
import glob
import shutil
import pytest
from unittest.mock import patch, MagicMock, call

# Add project root to path so we can import vdeps
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vdeps

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures'))

@pytest.fixture
def mock_subproc():
    with patch('subprocess.run') as mock:
        # Mock return value to be success (returncode 0)
        mock.return_value.returncode = 0
        yield mock

@pytest.fixture
def mock_shutil():
    with patch('shutil.copy2') as mock:
        yield mock

def test_linux_build(mock_subproc, mock_shutil):
    """
    Test behavior when running on Linux:
    - Should use Ninja generator
    - Should look for .a libraries
    - Should look for executables without extension
    """
    # Mock glob to return Linux-specific artifacts
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern and 'build_debug' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_lib' in pattern and 'build_release' in pattern:
            return ['/path/to/fake_lib/build_release/libfake_lib.a']
        elif 'fake_tool' in pattern and 'build_debug' in pattern:
            return ['/path/to/fake_tool/build_debug/fake_tool']
        elif 'fake_tool' in pattern and 'build_release' in pattern:
            return ['/path/to/fake_tool/build_release/fake_tool']
        return []

    # 1. Mock Platform and module-level constants
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'linux'), \
         patch('vdeps.LIB_EXT', '.a'):
        # 2. Mock __file__ so vdeps finds our fixture TOML
        # We need to set it on the module
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            # 3. Run Main
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # 4. Verify CMake Calls
    # Check for common Linux args in the first cmake call for fake_lib
    # Expected: cmake -S . -B ... -G Ninja ... -DOPTION_A=ON
    
    # Filter calls to find the configure step for fake_lib
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0] and '-S' in c[0][0]]
    
    assert len(cmake_calls) >= 1, "CMake configure should be called"
    
    # Check arguments of the first configure call (fake_lib)
    args = cmake_calls[0][0][0]
    assert '-G' in args and 'Ninja' in args, "Should use Ninja generator on Linux"
    assert '-DCMAKE_CXX_COMPILER=clang++' in args, "Should use Clang on Linux"
    assert '-DOPTION_A=ON' in args, "Should pass dependency-specific options"

    # 5. Verify Copy Calls
    # On Linux, we expect 'libfake_lib.a' and 'fake_tool' (no extension)
    copy_sources = [c[0][0] for c in mock_shutil.call_args_list]
    copy_filenames = [os.path.basename(s) for s in copy_sources]

    assert 'libfake_lib.a' in copy_filenames, "Should copy .a static libs on Linux"
    assert 'fake_lib.lib' not in copy_filenames, "Should NOT copy .lib files on Linux"
    
    assert 'fake_tool' in copy_filenames, "Should copy extensionless executables on Linux"
    assert 'fake_tool.exe' not in copy_filenames, "Should NOT copy .exe files on Linux"


def test_windows_build(mock_subproc, mock_shutil):
    """
    Test behavior when running on Windows:
    - Should use MSVC flags (no Ninja)
    - Should look for .lib libraries
    - Should look for .exe executables
    """
    # Mock glob to return Windows-specific artifacts
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern and 'build_debug' in pattern:
            return ['/mnt/games/code/vdeps/tests/fixtures/vdeps/fake_lib/build_debug/fake_lib.lib']
        elif 'fake_lib' in pattern and 'build_release' in pattern:
            return ['/mnt/games/code/vdeps/tests/fixtures/vdeps/fake_lib/build_release/fake_lib.lib']
        elif 'fake_tool' in pattern and 'build_debug' in pattern:
            return ['/mnt/games/code/vdeps/tests/fixtures/vdeps/fake_tool/build_debug/fake_tool.exe']
        elif 'fake_tool' in pattern and 'build_release' in pattern:
            return ['/mnt/games/code/vdeps/tests/fixtures/vdeps/fake_tool/build_release/fake_tool.exe']
        return []

    with patch('sys.platform', 'win32'), \
         patch('glob.glob', side_effect=mock_glob):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            # We also need to reload the module-level constants like IS_WINDOWS if they are cached?
            # vdeps.py sets:
            # IS_WINDOWS = (sys.platform == 'win32')
            # These are evaluated at import time. We must re-evaluate them or patch them.
            # Patching the global variables in vdeps is easier.
            with patch('vdeps.IS_WINDOWS', True), \
                 patch('vdeps.IS_MACOS', False), \
                 patch('vdeps.PLATFORM_TAG', 'win'), \
                 patch('vdeps.LIB_EXT', '.lib'):
                
                vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify CMake Calls
    cmake_calls = [c for c in mock_subproc.call_args_list if 'cmake' in c[0][0] and '-S' in c[0][0]]
    args = cmake_calls[0][0][0]
    
    # Should NOT have Ninja
    assert 'Ninja' not in args, "Should NOT use Ninja generator on Windows"
    
    # Should have MSVC runtime flags
    msvc_flag_present = any('CMAKE_MSVC_RUNTIME_LIBRARY' in a for a in args)
    assert msvc_flag_present, "Should set MSVC runtime library policy on Windows"

    # Verify Copy Calls
    copy_sources = [c[0][0] for c in mock_shutil.call_args_list]
    copy_filenames = [os.path.basename(s) for s in copy_sources]

    assert 'fake_lib.lib' in copy_filenames, "Should copy .lib files on Windows"
    assert 'fake_lib.a' not in copy_filenames, "Should NOT copy .a files on Windows"
    
def test_build_single_dependency(mock_subproc, mock_shutil):
    """
    Test building a single dependency by name
    """
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        return []

    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('sys.argv', ['vdeps.py', 'fake_lib']), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'linux'), \
         patch('vdeps.LIB_EXT', '.a'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify only fake_lib was processed
    captured = mock_subproc.call_args_list
    dep_names = set()
    for call in captured:
        cwd = call[1].get('cwd', '')
        if 'fake_lib' in cwd:
            dep_names.add('fake_lib')
        elif 'fake_tool' in cwd:
            dep_names.add('fake_tool')
    
    assert 'fake_lib' in dep_names
    assert 'fake_tool' not in dep_names


def test_build_multiple_dependencies(mock_subproc, mock_shutil):
    """
    Test building multiple dependencies by name
    """
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_tool' in pattern:
            return ['/path/to/fake_tool/build_debug/fake_tool']
        return []

    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('sys.argv', ['vdeps.py', 'fake_lib', 'fake_tool']), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'linux'), \
         patch('vdeps.LIB_EXT', '.a'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify both dependencies were processed
    captured = mock_subproc.call_args_list
    dep_names = set()
    for call in captured:
        cwd = call[1].get('cwd', '')
        if 'fake_lib' in cwd:
            dep_names.add('fake_lib')
        elif 'fake_tool' in cwd:
            dep_names.add('fake_tool')
    
    assert 'fake_lib' in dep_names
    assert 'fake_tool' in dep_names


def test_build_all_when_no_args(mock_subproc, mock_shutil):
    """
    Test backward compatibility: building all dependencies when no args provided
    """
    def mock_glob(pattern, recursive=False):
        if 'fake_lib' in pattern:
            return ['/path/to/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_tool' in pattern:
            return ['/path/to/fake_tool/build_debug/fake_tool']
        elif 'complex_lib' in pattern:
            return ['/path/to/complex_lib/build_debug/libcomplex_core.a']
        elif 'mixed_project' in pattern:
            return ['/path/to/mixed_project/build_debug/libmixed.a']
        elif 'multi_output' in pattern:
            return ['/path/to/multi_output/build_debug/libmulti.a']
        elif 'empty_config' in pattern:
            return ['/path/to/empty_config/build_debug/libempty_config.a']
        return []

    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('sys.argv', ['vdeps.py']), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.PLATFORM_TAG', 'linux'), \
         patch('vdeps.LIB_EXT', '.a'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file

    # Verify all dependencies were processed
    captured = mock_subproc.call_args_list
    dep_names = set()
    for call in captured:
        cwd = call[1].get('cwd', '')
        for dep in ['fake_lib', 'fake_tool', 'complex_lib', 'mixed_project', 'multi_output', 'empty_config']:
            if dep in cwd:
                dep_names.add(dep)
    
    assert len(dep_names) == 6
