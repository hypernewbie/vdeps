import os
import shutil
import pytest
import textwrap
from unittest.mock import patch

import vdeps

def test_install_custom_relative_path(tmp_path):
    """Test that install rules can copy to arbitrary paths relative to root."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)
    
    # Create a dummy file to "install" in the source dir
    artifact_file = dep_dir / "useful.txt"
    artifact_file.write_text("content")
    
    # Use build = false so it searches dep_dir
    toml_content = textwrap.dedent("""
        [[dependency]]
        name = "test_dep"
        rel_path = "test_dep"
        cmake_options = []
        build = false
        install = [
            { pattern = "useful.txt", target = "custom/destination/path" }
        ]
    """).strip()
    (root / "vdeps.toml").write_text(toml_content)
    
    # Mock necessary parts to run main() in the temp directory
    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
         patch('sys.argv', ['vdeps.py']), \
         patch('vdeps.__file__', str(root / "vdeps.py")), \
         patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / "vdeps.py")), \
         patch('vdeps.run_command'):
        
        vdeps.main()
    
    # Check if the file was copied to the custom destination
    expected_path = root / "custom" / "destination" / "path" / "useful.txt"
    assert expected_path.exists(), f"File should be copied to {expected_path}"
    assert expected_path.read_text() == "content"

def test_install_lib_shortcut_preserved(tmp_path):
    """Test that the 'lib' shortcut still works and uses platform/config subdir."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)
    
    artifact_file = dep_dir / "libtest.lib"
    artifact_file.write_text("libcontent")
    
    toml_content = textwrap.dedent("""
        [[dependency]]
        name = "test_dep"
        rel_path = "test_dep"
        cmake_options = []
        build = false
        install = [
            { pattern = "libtest.lib", target = "lib/extra" }
        ]
    """).strip()
    (root / "vdeps.toml").write_text(toml_content)
    
    with patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
         patch('sys.argv', ['vdeps.py']), \
         patch('vdeps.__file__', str(root / "vdeps.py")), \
         patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / "vdeps.py")), \
         patch('vdeps.run_command'):
        
        vdeps.main()
    
    # Check if the file was copied to lib/win_debug/extra
    expected_path = root / "lib" / "win_debug" / "extra" / "libtest.lib"
    assert expected_path.exists(), f"File should be copied to {expected_path}"
