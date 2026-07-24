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
    """Test that clean removes build directories and state when confirmed."""
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

    state_file = root / ".vdeps-state.json"
    state_file.write_text('{"schema_version": 1, "records": {}}', encoding="utf-8")
    
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
    assert not state_file.exists()

    captured = capsys.readouterr()
    assert "Removing state file" in captured.out
    assert "Clean complete." in captured.out


def test_clean_removes_mac_arch_build_dirs(capsys, tmp_path):
    """`--clean` on macOS enumerates build_<arch>_<sanitizer> and bare build_<arch> dirs.

    Per the architect: bare build_arm64_debug and build_x64_debug must be
    in the enumeration -- not just sanitizer cross-products -- or running
    `--arch arm64` builds would leak past a subsequent `--clean`.
    """
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    # Create arch-tagged build dirs (no sanitizer) and sanitizer cross-products
    # to verify they're all swept by --clean.
    build_arch_dirs = [
        dep_dir / "build_arm64_debug",
        dep_dir / "build_arm64_release",
        dep_dir / "build_x64_debug",
        dep_dir / "build_x64_release",
        dep_dir / "build_arm64_thread_debug",
        dep_dir / "build_x64_address_release",
    ]
    for d in build_arch_dirs:
        d.mkdir()

    # A non-arch dir (sanitizer-only) must also still get cleaned
    # (regression check -- we didn't break the existing non-arch enumeration).
    build_thread = dep_dir / "build_thread_debug"
    build_thread.mkdir()

    toml_content = """
    dependency = [
        { name = "test_dep", rel_path = "test_dep", cmake_options = [] }
    ]
    """
    (root / "vdeps.toml").write_text(toml_content)

    with patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / "vdeps.py")), \
         patch('vdeps.IS_MACOS', True), \
         patch('vdeps.IS_WINDOWS', False), \
         patch('vdeps.PLATFORM_TAG', 'mac'), \
         patch('builtins.input', return_value='clean'), \
         patch('sys.argv', ['vdeps.py', '--clean']), \
         patch('vdeps.__file__', str(root / 'vdeps.py')):

        with pytest.raises(SystemExit) as e:
            vdeps.main()
        assert e.value.code == 0

    for d in build_arch_dirs:
        assert not d.exists(), f"{d} should have been removed by --clean on macOS"
    assert not build_thread.exists(), "Sanitizer-only dir must still be cleaned"

    captured = capsys.readouterr()
    for d in build_arch_dirs:
        assert f"Removing {d}" in captured.out


def test_clean_does_not_enumerate_arch_dirs_on_windows(capsys, tmp_path):
    """On Windows, --arch isn't accepted, so the macOS arch prefix list must not run.

    Defense in depth: --clean is platform-agnostic, but the arch prefix
    enumeration is gated on IS_MACOS. Verify by running --clean on Windows
    with a 'build_arm64_debug' dir present and confirming it survives.
    """
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)
    leak_dir = dep_dir / "build_arm64_debug"
    leak_dir.mkdir()

    toml_content = """
    dependency = [
        { name = "test_dep", rel_path = "test_dep", cmake_options = [] }
    ]
    """
    (root / "vdeps.toml").write_text(toml_content)

    with patch('vdeps.os.path.dirname', return_value=str(root)), \
         patch('vdeps.os.path.abspath', return_value=str(root / 'vdeps.py')), \
         patch('vdeps.IS_MACOS', False), \
         patch('vdeps.IS_WINDOWS', True), \
         patch('vdeps.PLATFORM_TAG', 'win'), \
         patch('builtins.input', return_value='clean'), \
         patch('sys.argv', ['vdeps.py', '--clean']), \
         patch('vdeps.__file__', str(root / 'vdeps.py')):

        with pytest.raises(SystemExit):
            vdeps.main()

    # The Windows --clean enumeration should NOT have touched this dir.
    assert leak_dir.exists(), (
        "Windows --clean must not enumerate macOS arch dirs (cross-platform leak guard)"
    )
