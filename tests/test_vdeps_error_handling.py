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

def test_cmake_configure_failure(mock_subproc, mock_shutil, capsys):
    """
    Test that CMake configure failure causes exit with error
    """
    # Make subprocess.run return failure for cmake -S (configure)
    def side_effect(args, **kwargs):
        if args and args[0] == 'cmake' and '-S' in args:
            mock = MagicMock()
            mock.returncode = 1
            return mock
        return MagicMock(returncode=0)
    
    mock_subproc.side_effect = side_effect
    
    with patch('sys.platform', 'linux'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            # Should exit on error
            assert False, "Should have exited on CMake error"
        except SystemExit as e:
            assert e.code == 1, "Should exit with error code 1"
            captured = capsys.readouterr()
            assert "Error: Command failed" in captured.out
        finally:
            vdeps.__file__ = original_file

def test_cmake_build_failure(mock_subproc, mock_shutil, capsys):
    """
    Test that CMake build failure causes exit with error
    """
    # Make subprocess.run return failure for cmake --build
    def side_effect(args, **kwargs):
        if args and args[0] == 'cmake' and '--build' in args:
            mock = MagicMock()
            mock.returncode = 1
            return mock
        return MagicMock(returncode=0)
    
    mock_subproc.side_effect = side_effect
    
    with patch('sys.platform', 'linux'):
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            # Should exit on error
            assert False, "Should have exited on build error"
        except SystemExit as e:
            assert e.code == 1, "Should exit with error code 1"
            captured = capsys.readouterr()
            assert "Error: Command failed" in captured.out
        finally:
            vdeps.__file__ = original_file

def test_no_artifacts_found(mock_subproc, mock_shutil, capsys):
    """
    Test that when no artifacts are found, a warning is printed but execution continues
    """
    # Mock glob to return empty (no artifacts)
    with patch('sys.platform', 'linux'), \
         patch('glob.glob', return_value=[]), \
         patch('sys.argv', ['vdeps.py']):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            captured = capsys.readouterr()
            # Should print warnings but not exit
            assert "Warning: No artifacts copied" in captured.out
            assert "[SUCCESS] Processed dependencies:" in captured.out
        finally:
            vdeps.__file__ = original_file
def test_error_on_single_missing_dependency(mock_subproc, mock_shutil):
    """
    Test that requesting a non-existent dependency exits with error
    """
    with patch('sys.platform', 'linux'), \
         patch('sys.argv', ['vdeps.py', 'nonexistent_dep']):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            assert False, "Should have exited with error"
        except SystemExit as e:
            assert e.code == 1, "Should exit with error code 1"
        finally:
            vdeps.__file__ = original_file


def test_error_on_multiple_missing_dependencies(mock_subproc, mock_shutil):
    """
    Test that requesting multiple non-existent dependencies exits with error
    """
    with patch('sys.platform', 'linux'), \
         patch('sys.argv', ['vdeps.py', 'dep1', 'dep2', 'dep3']):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            assert False, "Should have exited with error"
        except SystemExit as e:
            assert e.code == 1, "Should exit with error code 1"
        finally:
            vdeps.__file__ = original_file


def test_error_partial_match_does_not_work(mock_subproc, mock_shutil):
    """
    Test that partial name matching doesn't work (exact name required)
    """
    # fake_lib exists, but "fake" is only a partial match
    with patch('sys.platform', 'linux'), \
         patch('sys.argv', ['vdeps.py', 'fake']):
        
        original_file = vdeps.__file__
        vdeps.__file__ = os.path.join(FIXTURES_DIR, 'dummy_script.py')
        
        try:
            vdeps.main()
            assert False, "Should have exited with error for partial match"
        except SystemExit as e:
            assert e.code == 1, "Should exit with error code 1"
        finally:
            vdeps.__file__ = original_file
