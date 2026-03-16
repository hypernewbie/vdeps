import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import vdeps

@pytest.fixture
def mock_subproc():
    with patch("subprocess.run") as mock:
        mock.return_value.returncode = 0
        yield mock

@pytest.fixture
def mock_shutil():
    with patch("shutil.copy2") as mock:
        yield mock

def test_cmake_options_variable_interpolation(mock_subproc, mock_shutil):
    """
    Test that ${PLATFORM_SUBDIR}, ${CONFIG_NAME}, and ${ROOT_DIR} 
    are correctly interpolated in cmake_options.
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "VarOptionsDep",
                "rel_path": "deps/var_opts",
                "cmake_options": [
                    "-DSPIRV_TOOLS_DIR=${ROOT_DIR}/lib/${PLATFORM_SUBDIR}_${CONFIG_NAME}",
                    "-DCONFIG_TYPE=${CONFIG_NAME}"
                ],
                "build": True,
                "install": []
            }
        ]
    }

    # Mock glob to avoid errors during copy phase
    def mock_glob(pattern, recursive=False):
        return []

    # Mock context: Windows with LLVM
    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('vdeps.os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', '--llvm', 'VarOptionsDep']),
        patch('glob.glob', side_effect=mock_glob),
        patch('vdeps.os.makedirs'),
        patch('vdeps.IS_WINDOWS', True),
        patch('vdeps.PLATFORM_TAG', 'win'),
        patch(
            'vdeps.get_llvm_tool_path',
            side_effect=lambda name: f"/mock/{name}.exe",
        ),
    ):
        vdeps.main()

    # Capture all cmake configure calls (arguments start with 'cmake', '-S')
    configure_calls = []
    for call_obj in mock_subproc.call_args_list:
        args = call_obj[0][0]
        if args[0] == "cmake" and args[1] == "-S":
            configure_calls.append(args)

    assert len(configure_calls) == 2, "Should configure twice (Debug and Release)"

    # --- Debug Config Check ---
    # Expected: 
    #   PLATFORM_SUBDIR = "win_llvm"
    #   CONFIG_NAME = "debug"
    #   path: .../lib/win_llvm_debug
    debug_call = configure_calls[0]
    
    # Verify build type
    assert any("CMAKE_BUILD_TYPE=Debug" in arg for arg in debug_call)
    
    # Verify interpolated options
    interpolated_path = None
    config_type = None
    for arg in debug_call:
        if arg.startswith("-DSPIRV_TOOLS_DIR="):
            interpolated_path = arg
        if arg.startswith("-DCONFIG_TYPE="):
            config_type = arg
            
    assert interpolated_path is not None
    # Use double backslashes for windows paths in check if necessary, but ROOT_DIR is standardized to forward slashes in vdeps.py
    # and we replaced os.sep with / in root_dir_cmake
    assert "lib/win_llvm_debug" in interpolated_path
    assert config_type == "-DCONFIG_TYPE=debug"


    # --- Release Config Check ---
    # Expected: 
    #   PLATFORM_SUBDIR = "win_llvm"
    #   CONFIG_NAME = "release"
    #   path: .../lib/win_llvm_release
    release_call = configure_calls[1]
    
    # Verify build type
    assert any("CMAKE_BUILD_TYPE=RelWithDebInfo" in arg for arg in release_call) # Windows release is RelWithDebInfo
    
    interpolated_path = None
    config_type = None
    for arg in release_call:
        if arg.startswith("-DSPIRV_TOOLS_DIR="):
            interpolated_path = arg
        if arg.startswith("-DCONFIG_TYPE="):
            config_type = arg

    assert interpolated_path is not None
    assert "lib/win_llvm_release" in interpolated_path
    assert config_type == "-DCONFIG_TYPE=release"


def test_cmake_options_standard_linux(mock_subproc, mock_shutil):
    """
    Test variable interpolation on standard Linux (no llvm).
    """
    mock_toml_data = {
        "dependency": [
            {
                "name": "LinuxVarDep",
                "rel_path": "deps/linux_var",
                "cmake_options": [
                    "-DOUTPUT_DIR=${PLATFORM_SUBDIR}/${CONFIG_NAME}"
                ],
                "build": True
            }
        ]
    }

    def mock_glob(pattern, recursive=False):
        return []

    with (
        patch('vdeps.tomllib.load', return_value=mock_toml_data),
        patch('os.path.exists', return_value=True),
        patch('sys.argv', ['vdeps.py', 'LinuxVarDep']),
        patch('glob.glob', side_effect=mock_glob),
        patch('os.makedirs'),
        patch('sys.platform', 'linux'),
        patch('vdeps.IS_WINDOWS', False),
        patch('vdeps.PLATFORM_TAG', 'linux')
    ):
        vdeps.main()

    configure_calls = [c[0][0] for c in mock_subproc.call_args_list if c[0][0][0] == "cmake" and c[0][0][1] == "-S"]
    assert len(configure_calls) == 2

    # Debug
    debug_call = configure_calls[0]
    found = False
    for arg in debug_call:
        if arg.startswith("-DOUTPUT_DIR="):
            assert "linux/debug" in arg
            found = True
    assert found

    # Release
    release_call = configure_calls[1]
    found = False
    for arg in release_call:
        if arg.startswith("-DOUTPUT_DIR="):
            assert "linux/release" in arg
            found = True
    assert found
