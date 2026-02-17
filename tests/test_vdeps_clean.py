import sys
import os
import pytest
from unittest.mock import patch
import vdeps

def test_clean_cancelled(capsys):
    """Test that clean is cancelled if user doesn't type 'clean'."""
    with patch('sys.argv', ['vdeps.py', '--clean']), patch('builtins.input', return_value='no'):
        with pytest.raises(SystemExit) as e:
            vdeps.main()
        assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Clean cancelled." in captured.out

def test_clean_success(capsys, tmp_path):
    """Test that clean removes build directories when confirmed."""
    # Setup a dummy project structure
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)
    
    # Create build directories for debug and release
    build_debug = dep_dir / "build_debug"
    build_debug.mkdir()
    build_release = dep_dir / "build_release"
    build_release.mkdir()
    
    # Create a temp dir
    temp_dir = root / "custom_temp"
    temp_dir.mkdir()
    dep_temp_build = temp_dir / "test_dep_debug"
    dep_temp_build.mkdir()
    
    # Create a vdeps.toml
    toml_content = """
    temp_dir = "custom_temp"
    dependency = [
        { name = "test_dep", rel_path = "test_dep", cmake_options = [] }
    ]
    """
    (root / "vdeps.toml").write_text(toml_content)
    
    # Mocking vdeps to use our tmp_path
    with patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / "vdeps.py")), \
         patch('builtins.input', return_value='clean'), \
         patch('sys.argv', ['vdeps.py', '--clean']), \
         patch('vdeps.__file__', str(root / "vdeps.py")):
        
        with pytest.raises(SystemExit) as e:
            vdeps.main()
        assert e.value.code == 0

    # Verify build directories are gone
    assert not build_debug.exists()
    assert not build_release.exists()
    # Verify temp dir is gone
    assert not temp_dir.exists()
    
    captured = capsys.readouterr()
    assert "Clean complete." in captured.out
