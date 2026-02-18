import sys
import os
import pytest
from unittest.mock import patch

# Add project root to path so we can import vdeps
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vdeps

def test_get_llvm_tool_path():
    """Test that LLVM tool paths are correctly resolved or fallback to name."""
    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.shutil.which', return_value="C:\\LLVM\\bin\\clang-cl.exe"):
        path = vdeps.get_llvm_tool_path("clang-cl")
        assert path == "C:/LLVM/bin/clang-cl.exe"

    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.shutil.which', return_value=None):
        path = vdeps.get_llvm_tool_path("clang-cl")
        assert path == "clang-cl"

def test_get_platform_cmake_args_windows_llvm():
    """Test that --llvm on Windows produces correct Clang+Ninja args with paths."""
    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.shutil.which', side_effect=lambda x: f"C:\\LLVM\\bin\\{x}"):
        args = vdeps.get_platform_cmake_args(cxx_standard=20, use_llvm=True)
        
        # Check for Ninja generator
        assert "-G" in args
        assert "Ninja" in args
        
        # Check for Clang-CL with path
        assert "-DCMAKE_C_COMPILER=C:/LLVM/bin/clang-cl.exe" in args
        assert "-DCMAKE_CXX_COMPILER=C:/LLVM/bin/clang-cl.exe" in args
        
        # Check for LLVM tools with paths
        assert "-DCMAKE_LINKER=C:/LLVM/bin/lld-link.exe" in args
        assert "-DCMAKE_NM=C:/LLVM/bin/llvm-nm.exe" in args
        assert "-DCMAKE_AR=C:/LLVM/bin/llvm-lib.exe" in args
        assert "-DCMAKE_RANLIB=C:/LLVM/bin/llvm-ranlib.exe" in args

        # Check for warning suppression
        assert any("-w" in arg for arg in args), "Should include -w flag for warning suppression"
        
        # Check for MSVC flags preservation (e.g. /W0, /EHsc)
        assert any("/W0" in arg for arg in args), "Should preserve /W0 flag"
        assert any("/EHsc" in arg for arg in args), "Should preserve /EHsc flag"

def test_get_platform_cmake_args_windows_default():
    """Test that default Windows behavior (MSVC) is preserved."""
    with patch('vdeps.IS_WINDOWS', True):
        args = vdeps.get_platform_cmake_args(cxx_standard=20, use_llvm=False)
        
        # Should NOT have Ninja
        assert "Ninja" not in args
        assert "-DCMAKE_C_COMPILER=clang-cl" not in args
        
        # Should have MSVC flags
        assert any("/W0" in arg for arg in args)

def test_get_platform_cmake_args_not_windows():
    """Test that use_llvm=True doesn't break non-Windows (or is ignored if not applicable)."""
    with patch('vdeps.IS_WINDOWS', False):
        # On Linux/Mac, it uses Clang/Ninja by default anyway.
        # We ensure it doesn't try to use clang-cl.
        args = vdeps.get_platform_cmake_args(cxx_standard=20, use_llvm=True)
        
        assert "Ninja" in args
        assert "-DCMAKE_C_COMPILER=clang" in args # Standard clang
        assert "-DCMAKE_C_COMPILER=clang-cl" not in args

def test_llvm_build_directory_name(tmp_path):
    """Test that --llvm uses build_llvm_ directory names on Windows."""
    # Setup dummy project
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)
    
    toml_content = """
    dependency = [
        { name = "test_dep", rel_path = "test_dep", cmake_options = [] }
    ]
    """
    (root / "vdeps.toml").write_text(toml_content)
    
    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
         patch('sys.argv', ['vdeps.py', '--llvm']), \
         patch('vdeps.__file__', str(root / "vdeps.py")), \
         patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / "vdeps.py")), \
         patch('vdeps.run_command') as mock_run:
        
        # We also need to mock glob to return nothing so it doesn't try to copy
        with patch('glob.glob', return_value=[]):
            vdeps.main()
            
    # Check if any cmake command used build_llvm_debug or build_llvm_release
    found_llvm_dir = False
    for call in mock_run.call_args_list:
        cmd = call[0][0]
        if any("build_llvm_" in arg for arg in cmd):
            found_llvm_dir = True
            break
            
    assert found_llvm_dir, "Should use build_llvm_ prefix when --llvm is set on Windows"

def test_llvm_output_directory_name(tmp_path):
    """Test that --llvm uses win_llvm_ output directory names on Windows."""
    # Setup dummy project
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)
    
    toml_content = """
    dependency = [
        { name = "test_dep", rel_path = "test_dep", cmake_options = [], libs = ["test_lib"] }
    ]
    """
    (root / "vdeps.toml").write_text(toml_content)
    
    def mock_glob(pattern, recursive=False):
        if "test_dep" in pattern and "build_llvm_debug" in pattern:
            return [str(root / "vdeps/test_dep/build_llvm_debug/test_lib.lib")]
        return []

    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
         patch('sys.argv', ['vdeps.py', '--llvm']), \
         patch('vdeps.__file__', str(root / "vdeps.py")), \
         patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / "vdeps.py")), \
         patch('vdeps.run_command'), \
         patch('glob.glob', side_effect=mock_glob), \
         patch('shutil.copy2') as mock_copy:
        
        vdeps.main()
            
    # Check if shutil.copy2 was called with a destination in win_llvm_debug or win_llvm_release
    found_win_llvm_output = False
    for call in mock_copy.call_args_list:
        dest = call[0][1]
        if "win_llvm_debug" in dest or "win_llvm_release" in dest:
            found_win_llvm_output = True
            break
            
    assert found_win_llvm_output, "Should copy to win_llvm_ directory when --llvm is set on Windows"

