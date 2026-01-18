import sys
import os
import pytest
from unittest.mock import patch, MagicMock

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

def test_debug_release_isolation(mock_subproc, mock_shutil):
    """
    Test that debug and release builds don't mix artifacts
    """
    def mock_glob(pattern, recursive=False):
        # Return dependency-specific paths to match actual patterns
        if 'fake_lib' in pattern and 'build_debug' in pattern:
            return ['/fake/path/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_lib' in pattern and 'build_release' in pattern:
            return ['/fake/path/fake_lib/build_release/libfake_lib.a']
        elif 'fake_tool' in pattern and 'build_debug' in pattern:
            return ['/fake/path/fake_tool/build_debug/fake_tool']
        elif 'fake_tool' in pattern and 'build_release' in pattern:
            return ['/fake/path/fake_tool/build_release/fake_tool']
        return []
    
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file
    
    # Verify copy calls separated by output directory
    copy_calls = mock_shutil.call_args_list
    
    debug_calls = [c for c in copy_calls if 'linux_debug' in c[0][1]]
    release_calls = [c for c in copy_calls if 'linux_release' in c[0][1]]
    
    # Should have both debug and release calls
    assert len(debug_calls) > 0, "Should copy debug artifacts"
    assert len(release_calls) > 0, "Should copy release artifacts"
    
    # Debug should not go to release dir
    for call in debug_calls:
        assert 'linux_release' not in call[0][1], "Debug artifacts should not go to release dir"
    
    # Release should not go to debug dir
    for call in release_calls:
        assert 'linux_debug' not in call[0][1], "Release artifacts should not go to debug dir"

def test_platform_output_dirs(mock_subproc, mock_shutil):
    """
    Test that platform-specific output directories are used correctly
    """
    def mock_glob(pattern, recursive=False):
        # Return dependency-specific paths to match actual patterns
        if 'fake_lib' in pattern and 'build_debug' in pattern:
            return ['/fake/path/fake_lib/build_debug/libfake_lib.a']
        elif 'fake_lib' in pattern and 'build_release' in pattern:
            return ['/fake/path/fake_lib/build_release/libfake_lib.a']
        elif 'fake_tool' in pattern and 'build_debug' in pattern:
            return ['/fake/path/fake_tool/build_debug/fake_tool']
        elif 'fake_tool' in pattern and 'build_release' in pattern:
            return ['/fake/path/fake_tool/build_release/fake_tool']
        return []
    
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file
    
    # Verify all copy calls use linux_ prefix
    copy_calls = mock_shutil.call_args_list
    
    for call in copy_calls:
        dest_dir = call[0][1]
        assert 'linux_' in dest_dir, f"Output dir should use platform prefix: {dest_dir}"
        assert 'mac_' not in dest_dir, "Should not use mac prefix on linux"
        assert 'win_' not in dest_dir, "Should not use win prefix on linux"

def test_multi_dependency_isolation(mock_subproc, mock_shutil):
    """
    Test that multiple dependencies don't interfere with each other
    """
    def mock_glob_function(pattern, recursive=False):
        # Return appropriate fake artifacts for different dependencies
        if 'fake_lib' in pattern:
            return ['/fake/path/libfake_lib.a']
        elif 'fake_tool' in pattern:
            return ['/fake/path/fake_tool']
        elif 'complex_lib' in pattern:
            return ['/fake/path/libcomplex_core.a', '/fake/path/libcomplex_utils.a']
        elif 'mixed_project' in pattern:
            return ['/fake/path/libmixed.a', '/fake/path/mixed_tool', '/fake/path/data.blob']
        elif 'empty_config' in pattern:
            return ['/fake/path/libempty_config.a']
        elif 'multi_output' in pattern:
            return ['/fake/path/libmulti_output.a']
        return []
    
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', side_effect=mock_glob_function):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file
    
    # Verify all dependencies were processed
    cmake_calls = mock_subproc.call_args_list
    
    # Flatten all args to strings for searching
    all_command_strings = []
    for call in cmake_calls:
        args = call[0][0] if call[0] else []
        if isinstance(args, list):
            all_command_strings.extend(str(arg) for arg in args)
        else:
            all_command_strings.append(str(args))
    
    # Should have references to each dependency
    dep_names = ['fake_lib', 'fake_tool', 'complex_lib', 'mixed_project', 'empty_config', 'multi_output']
    
    for dep_name in dep_names:
        found = any(dep_name in cmd for cmd in all_command_strings)
        assert found, f"Should process dependency {dep_name}"
    
    # Should copy artifacts from different dependencies
    copy_sources = [os.path.basename(c[0][0]) for c in mock_shutil.call_args_list]
    
    # Should have artifacts from multiple deps
    assert 'libfake_lib.a' in copy_sources
    assert 'fake_tool' in copy_sources
    assert any('complex' in f for f in copy_sources)
    assert any('mixed' in f for f in copy_sources)
    assert any('empty' in f for f in copy_sources)
