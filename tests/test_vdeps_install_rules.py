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

def test_no_build_install(mock_subproc, mock_shutil, mock_open_toml):
    """
    Test that build=False skips CMake and install rules copy files from source dir.
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "PrebuiltSDK",
                "rel_path": "sdks/prebuilt",
                "cmake_options": [],
                "build": False,
                "install": [
                    {"pattern": "lib/*.lib", "target": "lib"},
                    {"pattern": "bin/*.dll", "target": "tools"},
                    {"pattern": "data/*", "target": "tools/data"}
                ]
            }
        ]
    }

    def mock_glob(pattern, recursive=False):
        # Normalize pattern
        pattern = pattern.replace('\\', '/')
        
        # When build=False, search root is dep_dir
        if 'sdks/prebuilt' in pattern:
            if pattern.endswith('lib/*.lib'):
                return ['/path/to/sdks/prebuilt/lib/prebuilt.lib']
            elif pattern.endswith('bin/*.dll'):
                return ['/path/to/sdks/prebuilt/bin/prebuilt.dll']
            elif pattern.endswith('data/*'):
                return ['/path/to/sdks/prebuilt/data/config.json', '/path/to/sdks/prebuilt/data/assets.pak']
            elif pattern.endswith('/**/*'): # The recursive search for 'libs'/'executables' logic
                return []
        return []

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'PrebuiltSDK']),
        patch('glob.glob', side_effect=mock_glob),
        patch('os.makedirs')
    ):
        with patch('builtins.print') as mock_print:
            vdeps.main()
            
            # Verify CMake was NOT run
            assert not mock_subproc.called
            
            # Verify skipping message
            printed_lines = [call[0][0] for call in mock_print.call_args_list if call.args]
            assert any("Skipping build for PrebuiltSDK (build=false)" in line for line in printed_lines)

            # Verify Copy calls
            copy_calls = mock_shutil.call_args_list
            destinations = [call[0][1] for call in copy_calls]
            sources = [call[0][0] for call in copy_calls]
            
            # lib copy
            assert any('prebuilt.lib' in src for src in sources)
            assert any('lib' in dest and 'prebuilt.lib' in dest for dest in destinations)
            
            # tools copy
            assert any('prebuilt.dll' in src for src in sources)
            assert any('tools' in dest and 'prebuilt.dll' in dest for dest in destinations)
            
            # data copy (subdir)
            assert any('config.json' in src for src in sources)
            # Check destination has 'data' subdir (os.path.join usually handles this)
            # The destination path construction in vdeps.py joins target_base + target_subdir
            # We just check roughly if it went to the right place
            assert any('data' in dest and 'config.json' in dest for dest in destinations)

def test_install_with_build(mock_subproc, mock_shutil, mock_open_toml):
    """
    Test that install rules work even when build=True (copying from build dir).
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "BuiltLib",
                "rel_path": "libs/built_lib",
                "cmake_options": [],
                "build": True,
                "install": [
                    {"pattern": "generated/*.h", "target": "lib/include"}
                ]
            }
        ]
    }

    def mock_glob(pattern, recursive=False):
        pattern = pattern.replace('\\', '/')
        if 'build_debug' in pattern and pattern.endswith('generated/*.h'):
            return ['/path/to/build_debug/generated/my_header.h']
        elif 'build_release' in pattern and pattern.endswith('generated/*.h'):
            return ['/path/to/build_release/generated/my_header.h']
        return []

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'BuiltLib']),
        patch('glob.glob', side_effect=mock_glob),
        patch('os.makedirs')
    ):
         with patch('builtins.print'):
            vdeps.main()
            
            # Verify CMake WAS run
            assert mock_subproc.called
            
            # Verify Copy calls for generated header
            copy_calls = mock_shutil.call_args_list
            destinations = [call[0][1] for call in copy_calls]
            
            assert any('my_header.h' in dest and 'include' in dest for dest in destinations)

def test_install_invalid_target(mock_subproc, mock_shutil, mock_open_toml):
    """
    Test warning on invalid install target.
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "BadTarget",
                "rel_path": "bad",
                "cmake_options": [],
                "install": [
                    {"pattern": "*.txt", "target": "somewhere_else"}
                ]
            }
        ]
    }

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'BadTarget']),
        patch('glob.glob', return_value=['file.txt']),
        patch('os.makedirs')
    ):
         with patch('builtins.print') as mock_print:
            vdeps.main()
            
            printed_lines = [call[0][0] for call in mock_print.call_args_list if call.args]
            assert any("Unknown target base 'somewhere_else'" in line for line in printed_lines)
            
            # Should NOT copy
            assert not mock_shutil.called
