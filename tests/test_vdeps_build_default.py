import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vdeps

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
    original_open = open
    
    def side_effect(file, *args, **kwargs):
        # Check if we're opening vdeps.toml (handling potential path variations)
        if "vdeps.toml" in str(file):
            return MagicMock()
        return original_open(file, *args, **kwargs)
        
    with patch('builtins.open', side_effect=side_effect):
        yield

def test_build_by_default_false_skipped(mock_subproc, mock_shutil, mock_open_toml):
    """
    Test that dependencies with build_by_default = False are skipped when running without args.
    """
    # Mock TOML data
    mock_toml_data = {
        "dependency": [
            {
                "name": "DefaultDep",
                "rel_path": "default_dep",
                "cmake_options": [],
                "build_by_default": True
            },
            {
                "name": "OptionalDep",
                "rel_path": "optional_dep",
                "cmake_options": [],
                "build_by_default": False
            }
        ]
    }

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py']),
        patch('glob.glob', return_value=[]),
        patch('os.makedirs')
    ):
        
        # Capture print output to verify what's being built
        with patch('builtins.print') as mock_print:
            vdeps.main()
            
            # Check if "OptionalDep" was skipped
            printed_lines = [call[0][0] for call in mock_print.call_args_list if call.args]
            
            # Verify DefaultDep is built
            assert any("Processing Dependency: DefaultDep" in line for line in printed_lines)
            
            # Verify OptionalDep is NOT built
            assert not any("Processing Dependency: OptionalDep" in line for line in printed_lines)

def test_build_by_default_false_explicitly_requested(mock_subproc, mock_shutil, mock_open_toml):
    """
    Test that dependencies with build_by_default = False are built when explicitly requested.
    """
    # Mock TOML data
    mock_toml_data = {
        "dependency": [
            {
                "name": "DefaultDep",
                "rel_path": "default_dep",
                "cmake_options": [],
                "build_by_default": True
            },
            {
                "name": "OptionalDep",
                "rel_path": "optional_dep",
                "cmake_options": [],
                "build_by_default": False
            }
        ]
    }

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'OptionalDep']),
        patch('glob.glob', return_value=[]),
        patch('os.makedirs')
    ):
        
        # Capture print output to verify what's being built
        with patch('builtins.print') as mock_print:
            vdeps.main()
            
            # Check if "OptionalDep" was built
            printed_lines = [call[0][0] for call in mock_print.call_args_list if call.args]
            
            # Verify OptionalDep is built because it was requested
            assert any("Processing Dependency: OptionalDep" in line for line in printed_lines)
            
            # Verify DefaultDep is NOT built (since we requested specific one)
            assert not any("Processing Dependency: DefaultDep" in line for line in printed_lines)

def test_build_by_default_implicit_true(mock_subproc, mock_shutil, mock_open_toml):
    """
    Test that dependencies default to build_by_default = True if not specified.
    """
    # Mock TOML data - missing build_by_default key
    mock_toml_data = {
        "dependency": [
            {
                "name": "ImplicitDep",
                "rel_path": "implicit_dep",
                "cmake_options": []
            }
        ]
    }

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py']),
        patch('glob.glob', return_value=[]),
        patch('os.makedirs')
    ):
        
        # Capture print output to verify what's being built
        with patch('builtins.print') as mock_print:
            vdeps.main()
            
            # Check if "ImplicitDep" was built
            printed_lines = [call[0][0] for call in mock_print.call_args_list if call.args]
            
            assert any("Processing Dependency: ImplicitDep" in line for line in printed_lines)
