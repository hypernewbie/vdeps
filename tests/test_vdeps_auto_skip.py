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
    with patch("sys.argv", ["vdeps.py", *argv]), patch(
        "vdeps.__file__", str(root / "vdeps.py")
    ):
        vdeps.main()


def completed(returncode=0, stdout="", stderr=""):
    return type(
        "CompletedResult",
        (),
        {"returncode": returncode, "stdout": stdout, "stderr": stderr},
    )()


def make_subprocess_side_effect(head="abc123", clean=True, git_repo=True):
    def _run(command, cwd=None, env=None, shell=False, capture_output=False, text=False, **kwargs):
        if command[0] == "git":
            git_args = command[3:]
            if git_args == ["rev-parse", "--is-inside-work-tree"]:
                return completed(0 if git_repo else 128, "true\n" if git_repo else "")
            if git_args == ["rev-parse", "HEAD"]:
                return completed(0 if git_repo else 128, f"{head}\n" if git_repo else "")
            if git_args == ["status", "--porcelain"]:
                if not git_repo:
                    return completed(128, "")
                return completed(0, "" if clean else " M dirty.txt\n")
        return completed(0)

    return _run


def write_state(root, records, schema_version=vdeps.STATE_SCHEMA_VERSION):
    state_path = root / vdeps.STATE_FILE_NAME
    state_path.write_text(
        json.dumps({"schema_version": schema_version, "records": records}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def write_basic_dep_config(root):
    write_config(
        root,
        """
        [[dependency]]
        name = "demo"
        rel_path = "demo"
        cmake_options = []
        libs = ["demo"]
        """,
    )


def write_tracking_dep_config(root):
    write_config(
        root,
        """
        [[dependency]]
        name = "demo"
        rel_path = "demo"
        cmake_options = []
        libs = ["demo"]
        executables = ["tool"]
        extra_files = ["tool.exe", "note.txt"]
        install = [
            { pattern = "assets/*.bin", target = "tools/assets" },
            { pattern = "plugins/*.dll", target = "lib/plugins" },
        ]
        """,
    )


def create_basic_build_artifacts(dep_dir):
    for config in ("debug", "release"):
        write_file(dep_dir / f"build_{config}" / "demo.lib", "lib")


def create_tracking_build_artifacts(dep_dir):
    for config in ("debug", "release"):
        build_dir = dep_dir / f"build_{config}"
        write_file(build_dir / "demo.lib", "lib")
        write_file(build_dir / "tool.exe", "exe")
        write_file(build_dir / "note.txt", "note")
        write_file(build_dir / "assets" / "data.bin", "data")
        write_file(build_dir / "plugins" / "helper.dll", "dll")


def make_record(root, config_name, head="abc123", output_name="demo.lib", toolchain=None):
    if toolchain is None:
        toolchain = {
            "compiler_path": "C:/fake/cl.exe",
            "compiler_version": "fake-cl 1.0",
            "use_llvm": False,
            "use_dynamic_runtime": False,
        }
    return {
        "dep_name": "demo",
        "rel_path": "demo",
        "platform_subdir": "win",
        "config_name": config_name,
        "head": head,
        "outputs": [f"lib/win_{config_name}/{output_name}"],
        "updated_at": "2026-03-15T12:34:56Z",
        "schema_version": vdeps.STATE_SCHEMA_VERSION,
        "toolchain": dict(toolchain),
    }


DEFAULT_TOOLCHAIN = {
    "compiler_path": "C:/fake/cl.exe",
    "compiler_version": "fake-cl 1.0",
    "use_llvm": False,
    "use_dynamic_runtime": False,
}


def run_auto_skip(root, argv, state_writer=None):
    """Run vdeps.main with --auto-skip and a stub toolchain fingerprint."""
    if state_writer is not None:
        state_writer(root)
    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()),
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(root, argv)


@pytest.fixture
def windows_platform():
    with patch("vdeps.IS_WINDOWS", True), patch("vdeps.IS_MACOS", False), patch(
        "vdeps.PLATFORM_TAG", "win"
    ), patch("vdeps.LIB_EXT", ".lib"):
        yield


def test_auto_skip_skips_when_head_and_outputs_match(
    tmp_path, capsys, windows_platform
):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)

    write_file(tmp_path / "lib" / "win_debug" / "demo.lib", "debug")
    write_file(tmp_path / "lib" / "win_release" / "demo.lib", "release")

    write_state(
        tmp_path,
        {
            vdeps.get_state_record_key("demo", "demo", "win", "debug"): make_record(
                tmp_path, "debug"
            ),
            vdeps.get_state_record_key("demo", "demo", "win", "release"): make_record(
                tmp_path, "release"
            ),
        },
    )

    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()) as mock_run,
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls == []

    captured = capsys.readouterr()
    assert "--- Auto-skipping demo [Debug] (HEAD + outputs match) ---" in captured.out
    assert (
        "--- Auto-skipping demo [RelWithDebInfo] (HEAD + outputs match) ---"
        in captured.out
    )


@pytest.mark.parametrize(
    ("state_writer", "git_head", "clean_repo", "git_repo", "expected_reason"),
    [
        (lambda root: None, "abc123", True, True, "no cached state"),
        (
            lambda root: write_state(
                root,
                {
                    vdeps.get_state_record_key(
                        "demo", "demo", "win", "debug"
                    ): make_record(root, "debug"),
                    vdeps.get_state_record_key(
                        "demo", "demo", "win", "release"
                    ): make_record(root, "release"),
                },
            ),
            "def456",
            True,
            True,
            "HEAD changed",
        ),
        (
            lambda root: write_state(
                root,
                {
                    vdeps.get_state_record_key(
                        "demo", "demo", "win", "debug"
                    ): make_record(root, "debug"),
                    vdeps.get_state_record_key(
                        "demo", "demo", "win", "release"
                    ): make_record(root, "release"),
                },
            ),
            "abc123",
            False,
            True,
            "repo is dirty",
        ),
        (
            lambda root: write_state(
                root,
                {
                    vdeps.get_state_record_key(
                        "demo", "demo", "win", "debug"
                    ): make_record(root, "debug"),
                    vdeps.get_state_record_key(
                        "demo", "demo", "win", "release"
                    ): make_record(root, "release"),
                },
            ),
            "abc123",
            True,
            False,
            "not a git repo",
        ),
    ],
)
def test_auto_skip_falls_back_to_build_for_common_ineligible_cases(
    tmp_path,
    capsys,
    windows_platform,
    state_writer,
    git_head,
    clean_repo,
    git_repo,
    expected_reason,
):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    state_writer(tmp_path)

    with (
        patch(
            "subprocess.run",
            side_effect=make_subprocess_side_effect(
                head=git_head, clean=clean_repo, git_repo=git_repo
            ),
        ) as mock_run,
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls

    captured = capsys.readouterr()
    assert expected_reason in captured.out


def test_auto_skip_falls_back_to_build_when_record_is_missing(
    tmp_path, capsys, windows_platform
):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    write_state(tmp_path, {"other|dep|win|debug": make_record(tmp_path, "debug")})

    with patch(
        "subprocess.run", side_effect=make_subprocess_side_effect()
    ) as mock_run:
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls

    captured = capsys.readouterr()
    assert "Auto-skip unavailable for demo [Debug]: no cached state" in captured.out


def test_auto_skip_falls_back_to_build_when_output_is_missing(
    tmp_path, capsys, windows_platform
):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    write_file(tmp_path / "lib" / "win_debug" / "demo.lib", "debug")
    write_state(
        tmp_path,
        {
            vdeps.get_state_record_key("demo", "demo", "win", "debug"): make_record(
                tmp_path, "debug"
            ),
            vdeps.get_state_record_key("demo", "demo", "win", "release"): make_record(
                tmp_path, "release"
            ),
        },
    )

    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()) as mock_run,
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls

    captured = capsys.readouterr()
    assert "missing output lib/win_release/demo.lib" in captured.out


def test_successful_build_writes_state_with_tracked_outputs_and_dedupes(
    tmp_path, windows_platform
):
    write_tracking_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_tracking_build_artifacts(dep_dir)

    with patch("subprocess.run", side_effect=make_subprocess_side_effect()):
        run_main(tmp_path, ["demo"])

    state_path = tmp_path / vdeps.STATE_FILE_NAME
    assert state_path.exists()

    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_data["schema_version"] == vdeps.STATE_SCHEMA_VERSION

    debug_record = state_data["records"][
        vdeps.get_state_record_key("demo", "demo", "win", "debug")
    ]
    release_record = state_data["records"][
        vdeps.get_state_record_key("demo", "demo", "win", "release")
    ]

    expected_debug_outputs = {
        "lib/win_debug/plugins/helper.dll",
        "lib/win_debug/demo.lib",
        "tools/win_debug/tool.exe",
        "tools/win_debug/note.txt",
        "tools/win_debug/assets/data.bin",
    }
    expected_release_outputs = {
        "lib/win_release/plugins/helper.dll",
        "lib/win_release/demo.lib",
        "tools/win_release/tool.exe",
        "tools/win_release/note.txt",
        "tools/win_release/assets/data.bin",
    }

    assert set(debug_record["outputs"]) == expected_debug_outputs
    assert set(release_record["outputs"]) == expected_release_outputs
    assert len(debug_record["outputs"]) == len(set(debug_record["outputs"]))
    assert len(release_record["outputs"]) == len(set(release_record["outputs"]))
    assert debug_record["head"] == "abc123"
    assert release_record["head"] == "abc123"
    assert debug_record["updated_at"].endswith("Z")
    assert release_record["updated_at"].endswith("Z")


def test_zero_copied_output_runs_do_not_create_state_entry(tmp_path, windows_platform):
    write_config(
        tmp_path,
        """
        [[dependency]]
        name = "demo"
        rel_path = "demo"
        cmake_options = []
        libs = ["missing"]
        """,
    )
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    with patch("subprocess.run", side_effect=make_subprocess_side_effect()):
        run_main(tmp_path, ["demo"])

    assert not (tmp_path / vdeps.STATE_FILE_NAME).exists()


def test_invalid_corrupt_state_is_ignored_with_fallback_to_build(
    tmp_path, capsys, windows_platform
):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)
    (tmp_path / vdeps.STATE_FILE_NAME).write_text("{not json", encoding="utf-8")

    with patch(
        "subprocess.run", side_effect=make_subprocess_side_effect()
    ) as mock_run:
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls

    captured = capsys.readouterr()
    assert f"Warning: Could not read {vdeps.STATE_FILE_NAME}" in captured.out


def test_schema_mismatch_state_is_ignored_with_fallback_to_build(
    tmp_path, capsys, windows_platform
):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)
    write_state(tmp_path, {}, schema_version=vdeps.STATE_SCHEMA_VERSION + 1)

    with patch(
        "subprocess.run", side_effect=make_subprocess_side_effect()
    ) as mock_run:
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls

    captured = capsys.readouterr()
    assert "schema version mismatch" in captured.out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--auto-skip", "--clean"], "--auto-skip cannot be used with --clean"),
        (
            ["--auto-skip", "--generate-cmake"],
            "--auto-skip cannot be used with --generate-cmake",
        ),
    ],
)
def test_auto_skip_rejects_invalid_flag_combinations(
    tmp_path, argv, message, capsys, windows_platform
):
    write_basic_dep_config(tmp_path)

    with pytest.raises(SystemExit) as exc:
        run_main(tmp_path, argv)

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert message in captured.err


@pytest.mark.parametrize(
    "argv",
    [
        ["--auto-skip", "--build", "demo"],
        ["--auto-skip", "demo"],
        ["--auto-skip", "--llvm", "demo"],
    ],
)
def test_auto_skip_accepts_valid_flag_combinations(tmp_path, argv, windows_platform):
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    with patch(
        "subprocess.run", side_effect=make_subprocess_side_effect(git_repo=False)
    ) as mock_run:
        run_main(tmp_path, argv)

    cmake_calls = [call for call in mock_run.call_args_list if call.args[0][0] == "cmake"]
    assert cmake_calls


# --- Toolchain fingerprint tests ---


def test_get_compiler_info_resolves_clang_cl():
    """On Windows + --llvm, the resolver picks clang-cl.exe and captures --version."""
    completed_proc = type(
        "CompletedResult",
        (),
        {
            "returncode": 0,
            "stdout": "clang version 19.1.0\nTarget: x86_64-pc-windows-msvc\n",
            "stderr": "",
        },
    )()
    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.shutil.which", return_value="C:/LLVM/bin/clang-cl.exe"),
        patch("subprocess.run", return_value=completed_proc),
    ):
        path, version = vdeps.get_compiler_info(use_llvm=True)
    assert path == "C:/LLVM/bin/clang-cl.exe"
    assert version == "clang version 19.1.0"


def test_get_compiler_info_returns_none_path_when_missing():
    """When the compiler is not on PATH, return (None, None) without raising."""
    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.shutil.which", return_value=None),
    ):
        path, version = vdeps.get_compiler_info(use_llvm=False)
    assert path is None
    assert version is None


def test_get_compiler_info_returns_path_without_version_on_failure():
    """If the compiler exists but --version fails, we still capture the path."""
    failed_proc = type(
        "CompletedResult",
        (),
        {"returncode": 1, "stdout": "", "stderr": "boom"},
    )()
    with (
        patch("vdeps.IS_WINDOWS", True),
        patch("vdeps.shutil.which", return_value="C:/VS/cl.exe"),
        patch("subprocess.run", return_value=failed_proc),
    ):
        path, version = vdeps.get_compiler_info(use_llvm=False)
    assert path == "C:/VS/cl.exe"
    assert version is None


def test_get_toolchain_fingerprint_distinguishes_llvm():
    """The fingerprint changes when use_llvm flips, even with the same compiler info."""
    info = ("C:/LLVM/bin/clang-cl.exe", "clang version 19.0")
    with patch("vdeps.get_compiler_info", return_value=info):
        mt = vdeps.get_toolchain_fingerprint(use_llvm=False, use_dynamic_runtime=False)
        llvm = vdeps.get_toolchain_fingerprint(
            use_llvm=True, use_dynamic_runtime=False
        )
    assert mt != llvm
    assert mt["use_llvm"] is False
    assert llvm["use_llvm"] is True


def test_successful_build_writes_toolchain_fingerprint(tmp_path, windows_platform):
    """A successful build records the current toolchain fingerprint in the state file."""
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()),
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["demo"])

    state_data = json.loads(
        (tmp_path / vdeps.STATE_FILE_NAME).read_text(encoding="utf-8")
    )
    for config_name in ("debug", "release"):
        record = state_data["records"][
            vdeps.get_state_record_key("demo", "demo", "win", config_name)
        ]
        assert record["toolchain"] == DEFAULT_TOOLCHAIN


def test_auto_skip_rebuilds_when_compiler_path_changes(
    tmp_path, capsys, windows_platform
):
    """Mismatched compiler_path in the cached record forces a rebuild."""
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    stale_toolchain = dict(DEFAULT_TOOLCHAIN)
    stale_toolchain["compiler_path"] = "C:/old/cl.exe"
    write_state(
        tmp_path,
        {
            vdeps.get_state_record_key("demo", "demo", "win", "debug"): make_record(
                tmp_path, "debug", toolchain=stale_toolchain
            ),
            vdeps.get_state_record_key("demo", "demo", "win", "release"): make_record(
                tmp_path, "release", toolchain=stale_toolchain
            ),
        },
    )

    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()) as mock_run,
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [
        call for call in mock_run.call_args_list if call.args[0][0] == "cmake"
    ]
    assert cmake_calls
    captured = capsys.readouterr()
    assert "toolchain changed" in captured.out


def test_auto_skip_rebuilds_when_compiler_version_changes(
    tmp_path, capsys, windows_platform
):
    """Mismatched compiler_version in the cached record forces a rebuild."""
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    stale_toolchain = dict(DEFAULT_TOOLCHAIN)
    stale_toolchain["compiler_version"] = "Microsoft (R) C/C++ Optimizing Compiler Version 19.0"
    write_state(
        tmp_path,
        {
            vdeps.get_state_record_key("demo", "demo", "win", "debug"): make_record(
                tmp_path, "debug", toolchain=stale_toolchain
            ),
            vdeps.get_state_record_key("demo", "demo", "win", "release"): make_record(
                tmp_path, "release", toolchain=stale_toolchain
            ),
        },
    )

    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()) as mock_run,
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [
        call for call in mock_run.call_args_list if call.args[0][0] == "cmake"
    ]
    assert cmake_calls
    captured = capsys.readouterr()
    assert "toolchain changed" in captured.out


def test_auto_skip_rebuilds_when_record_lacks_toolchain(
    tmp_path, capsys, windows_platform
):
    """Old (pre-fingerprint) records force a rebuild so the fingerprint gets written."""
    write_basic_dep_config(tmp_path)
    dep_dir = tmp_path / "vdeps" / "demo"
    dep_dir.mkdir(parents=True)
    create_basic_build_artifacts(dep_dir)

    record = make_record(tmp_path, "debug")
    del record["toolchain"]
    write_state(
        tmp_path,
        {
            vdeps.get_state_record_key("demo", "demo", "win", "debug"): record,
            vdeps.get_state_record_key(
                "demo", "demo", "win", "release"
            ): make_record(tmp_path, "release"),
        },
    )

    with (
        patch("subprocess.run", side_effect=make_subprocess_side_effect()) as mock_run,
        patch("vdeps.get_toolchain_fingerprint", return_value=dict(DEFAULT_TOOLCHAIN)),
    ):
        run_main(tmp_path, ["--auto-skip", "demo"])

    cmake_calls = [
        call for call in mock_run.call_args_list if call.args[0][0] == "cmake"
    ]
    assert cmake_calls
    captured = capsys.readouterr()
    assert "toolchain changed" in captured.out
