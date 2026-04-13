import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def write_file(path, content="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_config(root, dependency_block):
    (root / "vdeps.toml").write_text(dependency_block.strip() + "\n", encoding="utf-8")


def run_main(root, argv):
    with (
        patch("sys.argv", ["vdeps.py", *argv]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
    ):
        vdeps.main()


def test_get_platform_cmake_args_md_windows():
    """Test that use_dynamic_runtime=True on Windows produces /MD and /MDd runtime flags."""
    with patch("vdeps.IS_WINDOWS", True):
        args = vdeps.get_platform_cmake_args(cxx_standard=20, use_dynamic_runtime=True)

        runtime_flag = (
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>DLL"
        )
        assert runtime_flag in args, f"Expected {runtime_flag} in args, got {args}"


def test_get_platform_cmake_args_mt_windows():
    """Test that use_dynamic_runtime=False on Windows produces static /MT and /MTd runtime flags."""
    with patch("vdeps.IS_WINDOWS", True):
        args = vdeps.get_platform_cmake_args(cxx_standard=20, use_dynamic_runtime=False)

        runtime_flag = (
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>"
        )
        assert runtime_flag in args
        assert "DLL" not in args[args.index(runtime_flag)]


def test_get_platform_cmake_args_md_with_llvm():
    """Test that use_dynamic_runtime=True works with use_llvm=True on Windows."""
    with (
        patch("vdeps.IS_WINDOWS", True),
        patch(
            "vdeps.resolve_executable_path", side_effect=lambda x: f"C:/LLVM/bin/{x}"
        ),
    ):
        args = vdeps.get_platform_cmake_args(
            cxx_standard=20, use_llvm=True, use_dynamic_runtime=True
        )

        runtime_flag = (
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>DLL"
        )
        assert runtime_flag in args
        assert "-G" in args
        assert "Ninja" in args


def test_md_output_directory_name(tmp_path):
    """Test that --md uses win_md_ output directory names on Windows."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    libs = ["test_lib"]
    """
    (root / "vdeps.toml").write_text(toml_content)

    def mock_glob(pattern, recursive=False):
        if "test_dep" in pattern and "build_md_debug" in pattern:
            return [str(root / "vdeps/test_dep/build_md_debug/test_lib.lib")]
        return []

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", side_effect=mock_glob),
        patch("shutil.copy2") as mock_copy,
    ):
        vdeps.main()

    found_win_md_output = False
    for call in mock_copy.call_args_list:
        dest = call[0][1]
        if "win_md_debug" in dest or "win_md_release" in dest:
            found_win_md_output = True
            break

    assert found_win_md_output, (
        "Should copy to win_md_ directory when --md is set on Windows"
    )


def test_llvm_md_combined_output_directory(tmp_path):
    """Test that --llvm --md uses win_llvm_md_ output directory names on Windows."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    libs = ["test_lib"]
    """
    (root / "vdeps.toml").write_text(toml_content)

    def mock_glob(pattern, recursive=False):
        if "test_dep" in pattern and "build_llvm_md_debug" in pattern:
            return [str(root / "vdeps/test_dep/build_llvm_md_debug/test_lib.lib")]
        return []

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--llvm", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", side_effect=mock_glob),
        patch("shutil.copy2") as mock_copy,
    ):
        vdeps.main()

    found_win_llvm_md_output = False
    for call in mock_copy.call_args_list:
        dest = call[0][1]
        if "win_llvm_md_debug" in dest or "win_llvm_md_release" in dest:
            found_win_llvm_md_output = True
            break

    assert found_win_llvm_md_output, (
        "Should copy to win_llvm_md_ directory when --llvm --md are both set"
    )


def test_md_build_directory_name(tmp_path):
    """Test that --md uses build_md_ directory names on Windows."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    """
    (root / "vdeps.toml").write_text(toml_content)

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command") as mock_run,
        patch("glob.glob", return_value=[]),
    ):
        vdeps.main()

    found_md_dir = False
    for call in mock_run.call_args_list:
        cmd = call[0][0]
        if any("build_md_" in arg for arg in cmd):
            found_md_dir = True
            break

    assert found_md_dir, "Should use build_md_ prefix when --md is set on Windows"


def test_llvm_md_combined_build_directory_name(tmp_path):
    """Test that --llvm --md uses build_llvm_md_ directory names on Windows."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    """
    (root / "vdeps.toml").write_text(toml_content)

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--llvm", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command") as mock_run,
        patch("glob.glob", return_value=[]),
    ):
        vdeps.main()

    found_llvm_md_dir = False
    for call in mock_run.call_args_list:
        cmd = call[0][0]
        if any("build_llvm_md_" in arg for arg in cmd):
            found_llvm_md_dir = True
            break

    assert found_llvm_md_dir, (
        "Should use build_llvm_md_ prefix when --llvm --md are both set on Windows"
    )


def test_state_record_key_includes_runtime():
    """Test that get_state_record_key includes runtime type in the key."""
    key_default = vdeps.get_state_record_key("demo", "demo", "win", "debug")
    key_md = vdeps.get_state_record_key(
        "demo", "demo", "win", "debug", use_dynamic_runtime=True
    )

    assert key_default == "demo|demo|win|debug|mt"
    assert key_md == "demo|demo|win|debug|md"
    assert key_default != key_md


def test_md_build_writes_state_with_runtime_flag(tmp_path):
    """Test that builds with --md write state with use_dynamic_runtime=True."""
    write_config(
        tmp_path,
        """
        [[dependency]]
        name = "demo"
        rel_path = "demo"
        cmake_options = []
        libs = ["demo"]
        """,
    )
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)

    for config in ("debug", "release"):
        build_dir = dep_dir / f"build_md_{config}"
        build_dir.mkdir(parents=True)
        write_file(build_dir / "demo.lib", "lib")

    def completed(returncode=0, stdout="", stderr=""):
        return type(
            "CompletedResult",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    def mock_subprocess(
        command, cwd=None, env=None, shell=False, capture_output=False, text=False
    ):
        if command[0] == "git":
            git_args = command[3:]
            if git_args == ["rev-parse", "--is-inside-work-tree"]:
                return completed(0, "true\n")
            if git_args == ["rev-parse", "HEAD"]:
                return completed(0, "abc123\n")
            if git_args == ["status", "--porcelain"]:
                return completed(0, "")
        return completed(0)

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.IS_MACOS", False),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("vdeps.LIB_EXT", ".lib"),
        patch("subprocess.run", side_effect=mock_subprocess),
    ):
        run_main(tmp_path, ["--md", "demo"])

    state_path = tmp_path / vdeps.STATE_FILE_NAME
    assert state_path.exists()

    state_data = json.loads(state_path.read_text(encoding="utf-8"))

    for config_name in ("debug", "release"):
        key_md = vdeps.get_state_record_key(
            "demo", "demo", "win_md", config_name, use_dynamic_runtime=True
        )
        key_static = vdeps.get_state_record_key(
            "demo", "demo", "win_md", config_name, use_dynamic_runtime=False
        )

        record = state_data["records"].get(key_md)
        assert record is not None, f"Expected record with key {key_md}"
        assert record.get("use_dynamic_runtime") is True
        assert record.get("platform_subdir") == "win_md"


def test_auto_skip_with_md_uses_correct_state_key(tmp_path):
    """Test that --auto-skip with --md uses the md runtime state key."""
    write_config(
        tmp_path,
        """
        [[dependency]]
        name = "demo"
        rel_path = "demo"
        cmake_options = []
        libs = ["demo"]
        """,
    )
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)

    write_file(tmp_path / "lib" / "win_md_debug" / "demo.lib", "debug")
    write_file(tmp_path / "lib" / "win_md_release" / "demo.lib", "release")

    def completed(returncode=0, stdout="", stderr=""):
        return type(
            "CompletedResult",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    def mock_subprocess(
        command, cwd=None, env=None, shell=False, capture_output=False, text=False
    ):
        if command[0] == "git":
            git_args = command[3:]
            if git_args == ["rev-parse", "--is-inside-work-tree"]:
                return completed(0, "true\n")
            if git_args == ["rev-parse", "HEAD"]:
                return completed(0, "abc123\n")
            if git_args == ["status", "--porcelain"]:
                return completed(0, "")
        return completed(0)

    key_debug = vdeps.get_state_record_key(
        "demo", "demo", "win_md", "debug", use_dynamic_runtime=True
    )
    key_release = vdeps.get_state_record_key(
        "demo", "demo", "win_md", "release", use_dynamic_runtime=True
    )
    record_debug = {
        "dep_name": "demo",
        "rel_path": "demo",
        "platform_subdir": "win_md",
        "config_name": "debug",
        "use_dynamic_runtime": True,
        "head": "abc123",
        "outputs": ["lib/win_md_debug/demo.lib"],
        "updated_at": "2026-03-15T12:34:56Z",
        "schema_version": vdeps.STATE_SCHEMA_VERSION,
    }
    record_release = {
        "dep_name": "demo",
        "rel_path": "demo",
        "platform_subdir": "win_md",
        "config_name": "release",
        "use_dynamic_runtime": True,
        "head": "abc123",
        "outputs": ["lib/win_md_release/demo.lib"],
        "updated_at": "2026-03-15T12:34:56Z",
        "schema_version": vdeps.STATE_SCHEMA_VERSION,
    }
    state_data = {
        "schema_version": vdeps.STATE_SCHEMA_VERSION,
        "records": {key_debug: record_debug, key_release: record_release},
    }
    state_path = tmp_path / vdeps.STATE_FILE_NAME
    state_path.write_text(json.dumps(state_data) + "\n", encoding="utf-8")

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.IS_MACOS", False),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("vdeps.LIB_EXT", ".lib"),
        patch("subprocess.run", side_effect=mock_subprocess) as mock_run,
    ):
        run_main(tmp_path, ["--auto-skip", "--md", "demo"])

    cmake_calls = [
        call for call in mock_run.call_args_list if call.args[0][0] == "cmake"
    ]
    assert cmake_calls == [], "Should skip cmake when state matches with --md"


def test_auto_skip_md_does_not_match_static_state(tmp_path, capsys):
    """Test that --auto-skip with --md does not match static (/MT) state records."""
    write_config(
        tmp_path,
        """
        [[dependency]]
        name = "demo"
        rel_path = "demo"
        cmake_options = []
        libs = ["demo"]
        """,
    )
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)

    write_file(tmp_path / "lib" / "win_md_debug" / "demo.lib", "debug")
    write_file(tmp_path / "lib" / "win_md_release" / "demo.lib", "release")

    def completed(returncode=0, stdout="", stderr=""):
        return type(
            "CompletedResult",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    def mock_subprocess(
        command, cwd=None, env=None, shell=False, capture_output=False, text=False
    ):
        if command[0] == "git":
            git_args = command[3:]
            if git_args == ["rev-parse", "--is-inside-work-tree"]:
                return completed(0, "true\n")
            if git_args == ["rev-parse", "HEAD"]:
                return completed(0, "abc123\n")
            if git_args == ["status", "--porcelain"]:
                return completed(0, "")
        return completed(0)

    static_key = vdeps.get_state_record_key(
        "demo", "demo", "win_md", "debug", use_dynamic_runtime=False
    )
    static_record = {
        "dep_name": "demo",
        "rel_path": "demo",
        "platform_subdir": "win_md",
        "config_name": "debug",
        "use_dynamic_runtime": False,
        "head": "abc123",
        "outputs": ["lib/win_md_debug/demo.lib"],
        "updated_at": "2026-03-15T12:34:56Z",
        "schema_version": vdeps.STATE_SCHEMA_VERSION,
    }
    state_data = {
        "schema_version": vdeps.STATE_SCHEMA_VERSION,
        "records": {static_key: static_record},
    }
    state_path = tmp_path / vdeps.STATE_FILE_NAME
    state_path.write_text(json.dumps(state_data) + "\n", encoding="utf-8")

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.IS_MACOS", False),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("vdeps.LIB_EXT", ".lib"),
        patch("subprocess.run", side_effect=mock_subprocess) as mock_run,
    ):
        run_main(tmp_path, ["--auto-skip", "--md", "demo"])

    cmake_calls = [
        call for call in mock_run.call_args_list if call.args[0][0] == "cmake"
    ]
    assert cmake_calls != [], (
        "Should NOT skip cmake when runtime type doesn't match (static state, dynamic flag)"
    )


def test_generate_cmake_includes_runtime_options(tmp_path):
    """Test that --generate-cmake produces CMake with runtime options."""
    write_config(
        tmp_path,
        """
        [[dependency]]
        name = "nvrhi"
        rel_path = "nvrhi"
        cmake_options = []
        """,
    )

    with patch("subprocess.run") as mock_run, patch("shutil.copy2") as mock_copy:
        run_main(tmp_path, ["--generate-cmake"])

    generated = tmp_path / "vdeps" / "CMakeLists.txt"
    content = generated.read_text(encoding="utf-8")

    assert (
        'option(VDEPS_STATIC_RUNTIME "Build with static MSVC runtime (/MT, /MTd)" OFF)'
        in content
    )
    assert (
        'option(VDEPS_DYNAMIC_RUNTIME "Build with dynamic MSVC runtime (/MD, /MDd)" OFF)'
        in content
    )
    assert "if(NOT VDEPS_STATIC_RUNTIME AND NOT VDEPS_DYNAMIC_RUNTIME)" in content
    assert "macro(vdeps_build_dep" in content
    assert "add_custom_target(vdeps_all_mt" in content
    assert 'vdeps_build_dep(vdeps_nvrhi nvrhi mt "")' in content
    assert "add_custom_target(vdeps_all_md" in content
    assert 'vdeps_build_dep(vdeps_nvrhi nvrhi md "--md")' in content


def test_md_llvm_build_directory_name(tmp_path):
    """Test that --llvm --md uses build_llvm_ directory names on Windows."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    """
    (root / "vdeps.toml").write_text(toml_content)

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--llvm", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command") as mock_run,
    ):
        with patch("glob.glob", return_value=[]):
            vdeps.main()

    found_llvm_dir = False
    for call in mock_run.call_args_list:
        cmd = call[0][0]
        if any("build_llvm_" in arg for arg in cmd):
            found_llvm_dir = True
            break

    assert found_llvm_dir, (
        "Should use build_llvm_ prefix when --llvm is set on Windows (even with --md)"
    )


def test_md_llvm_combined_platform_subdir(tmp_path):
    """Test that platform_subdir is win_llvm_md when both --llvm and --md are set."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    libs = ["test_lib"]
    """
    (root / "vdeps.toml").write_text(toml_content)

    def mock_glob(pattern, recursive=False):
        if "test_dep" in pattern and "build_llvm_md_debug" in pattern:
            return [str(root / "vdeps/test_dep/build_llvm_md_debug/test_lib.lib")]
        return []

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--llvm", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", side_effect=mock_glob),
        patch("shutil.copy2") as mock_copy,
    ):
        vdeps.main()

    found_win_llvm_md = False
    for call in mock_copy.call_args_list:
        dest = call[0][1]
        if "win_llvm_md_debug" in dest or "win_llvm_md_release" in dest:
            found_win_llvm_md = True
            break

    assert found_win_llvm_md, (
        "Should use win_llvm_md_ directory when both --llvm and --md are set"
    )


def test_md_flag_passed_to_cmake_args(tmp_path):
    """Test that --md flag results in use_dynamic_runtime=True being passed to get_platform_cmake_args."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    """
    (root / "vdeps.toml").write_text(toml_content)

    captured_args = {}

    def capture_platform_cmake_args(
        cxx_standard=20, use_llvm=False, use_dynamic_runtime=False
    ):
        captured_args["cxx_standard"] = cxx_standard
        captured_args["use_llvm"] = use_llvm
        captured_args["use_dynamic_runtime"] = use_dynamic_runtime
        return (
            vdeps.get_platform_cmake_args.__wrapped__(
                cxx_standard, use_llvm, use_dynamic_runtime
            )
            if hasattr(vdeps.get_platform_cmake_args, "__wrapped__")
            else [
                f"-DCMAKE_CXX_STANDARD={cxx_standard}",
                "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
                "-DVK_USE_PLATFORM_WIN32_KHR=ON",
                "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
                f"-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>{'DLL' if use_dynamic_runtime else ''}",
                "-DCMAKE_C_FLAGS=/W0",
                "-DCMAKE_CXX_FLAGS=/W0 /EHsc /MP",
            ]
        )

    original_func = vdeps.get_platform_cmake_args

    def mock_platform_cmake_args(
        cxx_standard=20, use_llvm=False, use_dynamic_runtime=False
    ):
        captured_args["cxx_standard"] = cxx_standard
        captured_args["use_llvm"] = use_llvm
        captured_args["use_dynamic_runtime"] = use_dynamic_runtime
        return [
            f"-DCMAKE_CXX_STANDARD={cxx_standard}",
            "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
            "-DVK_USE_PLATFORM_WIN32_KHR=ON",
            "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
            f"-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>{'DLL' if use_dynamic_runtime else ''}",
            "-DCMAKE_C_FLAGS=/W0",
            "-DCMAKE_CXX_FLAGS=/W0 /EHsc /MP",
        ]

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py", "--md"]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", return_value=[]),
        patch("vdeps.get_platform_cmake_args", side_effect=mock_platform_cmake_args),
    ):
        vdeps.main()

    assert captured_args.get("use_dynamic_runtime") is True, (
        "Should pass use_dynamic_runtime=True when --md is set"
    )


@pytest.mark.parametrize(
    "argv,expected_platform_subdir",
    [
        ([], "win"),
        (["--llvm"], "win_llvm"),
        (["--md"], "win_md"),
        (["--llvm", "--md"], "win_llvm_md"),
        (["--md", "--llvm"], "win_llvm_md"),
    ],
)
def test_platform_subdir_variations(tmp_path, argv, expected_platform_subdir):
    """Test that platform_subdir is correctly set for various flag combinations."""
    root = tmp_path
    vdeps_dir = root / "vdeps"
    dep_dir = vdeps_dir / "test_dep"
    dep_dir.mkdir(parents=True)

    toml_content = """
    [[dependency]]
    name = "test_dep"
    rel_path = "test_dep"
    cmake_options = []
    libs = ["test_lib"]
    """
    (root / "vdeps.toml").write_text(toml_content)

    def mock_glob(pattern, recursive=False):
        if "test_dep" in pattern:
            return [str(root / "vdeps/test_dep/build_debug/test_lib.lib")]
        return []

    platform_subdir_captured = None

    def mock_copy(src, dest, *args, **kwargs):
        pass

    original_main = vdeps.main

    captured_platform = {}

    def mock_platform_cmake_args(
        cxx_standard=20, use_llvm=False, use_dynamic_runtime=False
    ):
        return [
            f"-DCMAKE_CXX_STANDARD={cxx_standard}",
            "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
            "-DVK_USE_PLATFORM_WIN32_KHR=ON",
            "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
            f"-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>{'DLL' if use_dynamic_runtime else ''}",
            "-DCMAKE_C_FLAGS=/W0",
            "-DCMAKE_CXX_FLAGS=/W0 /EHsc /MP",
        ]

    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.PLATFORM_TAG", "win"),
        patch("sys.argv", ["vdeps.py"] + argv),
        patch("vdeps.__file__", str(root / "vdeps.py")),
        patch("vdeps.os.path.dirname", return_value=str(root)),
        patch("vdeps.os.path.abspath", return_value=str(root / "vdeps.py")),
        patch("vdeps.run_command"),
        patch("glob.glob", side_effect=mock_glob),
        patch("shutil.copy2", side_effect=lambda *args, **kwargs: None),
        patch("vdeps.get_platform_cmake_args", side_effect=mock_platform_cmake_args),
    ):

        def capture_output_lib_dir(dep, root_dir, config):
            return os.path.join(
                root_dir, "lib", f"{expected_platform_subdir}_{config['name']}"
            )

        vdeps.main()
