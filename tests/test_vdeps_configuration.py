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

def test_complex_lib_multiple_libs(mock_subproc, mock_shutil):
    """
    Test that complex_lib copies all specified libraries (core and utils)
    and ignores the extras library that wasn't listed in TOML
    """
    with patch('sys.platform', 'linux'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file
    
    # Verify copy was called
    copy_sources = [c[0][0] for c in mock_shutil.call_args_list]
    copy_filenames = [os.path.basename(s) for s in copy_sources]
    
    # Should copy complex_core and complex_utils (both debug and release)
    # Note: debug/release is in the build_dir path, not in filename
    assert any('libcomplex_core.a' in f for f in copy_filenames), "Should copy complex_core"
    assert any('libcomplex_utils.a' in f for f in copy_filenames), "Should copy complex_utils"
    
    # Should NOT copy complex_extras (not listed in TOML)
    extras_files = [f for f in copy_filenames if 'extras' in f]
    assert len(extras_files) == 0, "Should NOT copy complex_extras"
    
    # Should copy executables from other deps too
    assert any('fake_tool' in f and '.exe' not in f for f in copy_filenames), "Should copy executables"

def test_mixed_project_all_artifact_types(mock_subproc, mock_shutil):
    """
    Test mixed_project which has libs, executables, and extra_files
    """
    with patch('sys.platform', 'linux'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file
    
    # Verify copy was called
    copy_sources = [c[0][0] for c in mock_shutil.call_args_list]
    copy_filenames = [os.path.basename(s) for s in copy_sources]
    
    # Should copy library (same filename for debug and release, different build dirs)
    assert any('libmixed.a' in f for f in copy_filenames), "Should copy mixed lib"
    
    # Should copy executable (same filename for debug and release)
    assert any('mixed_tool' in f and '.exe' not in f for f in copy_filenames), "Should copy mixed_tool"
    
    # Should copy extra files (same filename for debug and release)
    assert any('data.blob' in f for f in copy_filenames), "Should copy data.blob"

def test_lib_copy_all_when_null(mock_subproc, mock_shutil):
    """
    Test empty_config which has no 'libs' field - should copy all .a files
    """
    with patch('sys.platform', 'linux'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
        finally:
            vdeps.__file__ = original_file
    
    # Verify copy was called
    copy_sources = [c[0][0] for c in mock_shutil.call_args_list]
    copy_filenames = [os.path.basename(s) for s in copy_sources]
    
    # Should copy ALL libraries (4 libraries x 2 configurations = 8 files)
    # Note: debug/release is in the build_dir path, not in filename
    assert sum('libemptyfoo.a' in f for f in copy_filenames) == 2, "Should copy empty_foo for debug and release"
    assert sum('libemptybar.a' in f for f in copy_filenames) == 2, "Should copy empty_bar for debug and release"
    assert sum('libemptybaz.a' in f for f in copy_filenames) == 2, "Should copy empty_baz for debug and release"
    assert sum('libemptyqux.a' in f for f in copy_filenames) == 2, "Should copy empty_qux for debug and release"
