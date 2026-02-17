import sys
import os
import pytest
from unittest.mock import patch

# Add project root to path so we can import vdeps
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vdeps

def test_get_platform_cmake_args_windows_llvm():
    """Test that --llvm on Windows produces correct Clang+Ninja args."""
    with patch('vdeps.IS_WINDOWS', True):
        args = vdeps.get_platform_cmake_args(cxx_standard=20, use_llvm=True)
        
        # Check for Ninja generator
        assert "-G" in args
        assert "Ninja" in args
        
        # Check for Clang-CL
        assert "-DCMAKE_C_COMPILER=clang-cl" in args
        assert "-DCMAKE_CXX_COMPILER=clang-cl" in args
        
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

