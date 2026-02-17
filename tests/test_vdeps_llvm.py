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
