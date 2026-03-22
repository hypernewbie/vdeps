import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def write_config(root, content):
    (root / "vdeps.toml").write_text(content, encoding="utf-8")


def run_main(root, argv):
    with (
        patch("sys.argv", ["vdeps.py", *argv]),
        patch("vdeps.__file__", str(root / "vdeps.py")),
    ):
        vdeps.main()


def get_cmake_content(tmp_path):
    with patch("subprocess.run"), patch("shutil.copy2"):
        run_main(tmp_path, ["--generate-cmake"])
    generated = tmp_path / "vdeps" / "CMakeLists.txt"
    return generated.read_text(encoding="utf-8")


class TestDefaultStatic:
    def test_default_generates_mt_targets_only(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all_mt)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi mt "")' in content
        assert "add_dependencies(vdeps_all vdeps_all_mt)" in content

    def test_default_generates_vdeps_all_md_conditional(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "if(VDEPS_DYNAMIC_RUNTIME)" in content
        assert "add_custom_target(vdeps_all_md" in content


class TestStaticExplicit:
    def test_static_runtime_generates_mt_targets(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all_mt)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi mt "")' in content


class TestDynamicOnly:
    def test_dynamic_runtime_generates_md_targets(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all_md)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi md "--md")' in content


class TestBothRuntimes:
    def test_both_flags_generates_mt_and_md_targets(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all_mt)" in content
        assert "add_custom_target(vdeps_all_md)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi mt "")' in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi md "--md")' in content

    def test_vdeps_all_depends_on_both_variants(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []

[[dependency]]
name = "vulkan"
rel_path = "vulkan"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_dependencies(vdeps_all" in content
        assert "vdeps_all_mt" in content
        assert "vdeps_all_md" in content


class TestLLVMVariants:
    def test_llvm_flag_generates_llvm_mt_targets(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "if(VDEPS_USE_LLVM)" in content
        assert "add_custom_target(vdeps_all_llvm_mt)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi llvm_mt "--llvm")' in content

    def test_llvm_and_dynamic_generates_llvm_md_targets(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all_llvm_md)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi llvm_md "--llvm --md")' in content

    def test_llvm_with_both_runtimes_generates_all_llvm_variants(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all_llvm_mt)" in content
        assert "add_custom_target(vdeps_all_llvm_md)" in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi llvm_mt "--llvm")' in content
        assert 'vdeps_build_dep(vdeps_nvrhi nvrhi llvm_md "--llvm --md")' in content


class TestMultipleDependencies:
    def test_multiple_deps_all_have_variants(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []

[[dependency]]
name = "vulkan"
rel_path = "vulkan"
cmake_options = []

[[dependency]]
name = "shader-make"
rel_path = "shader-make"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "vdeps_nvrhi_mt" in content
        assert "vdeps_vulkan_mt" in content
        assert "vdeps_shader_make_mt" in content
        assert (
            "add_dependencies(vdeps_all_mt vdeps_nvrhi_mt vdeps_vulkan_mt vdeps_shader_make_mt)"
            in content
        )


class TestMacroDefinition:
    def test_vdeps_build_dep_macro_is_defined(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "macro(vdeps_build_dep" in content
        assert "endmacro()" in content
        assert "${Python3_EXECUTABLE}" in content
        assert '"${CMAKE_CURRENT_LIST_DIR}/../vdeps.py"' in content
        assert "--build --auto-skip" in content


class TestOptions:
    def test_all_three_options_present(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert (
            'option(VDEPS_USE_LLVM "Use Clang/LLVM compiler on Windows" OFF)' in content
        )
        assert (
            'option(VDEPS_STATIC_RUNTIME "Build with static MSVC runtime (/MT, /MTd)" OFF)'
            in content
        )
        assert (
            'option(VDEPS_DYNAMIC_RUNTIME "Build with dynamic MSVC runtime (/MD, /MDd)" OFF)'
            in content
        )

    def test_default_logic_present(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "if(NOT VDEPS_STATIC_RUNTIME AND NOT VDEPS_DYNAMIC_RUNTIME)" in content
        assert "set(VDEPS_STATIC_RUNTIME ON)" in content


class TestTargetNaming:
    def test_target_suffix_format(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "test-dep"
rel_path = "test-dep"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "vdeps_test_dep_mt" in content
        assert "vdeps_test_dep_md" in content
        assert "vdeps_test_dep_llvm_mt" in content
        assert "vdeps_test_dep_llvm_md" in content

    def test_aggregate_target_naming(self, tmp_path):
        write_config(
            tmp_path,
            """
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)
        assert "add_custom_target(vdeps_all)" in content
        assert "add_custom_target(vdeps_all_mt)" in content
        assert "add_custom_target(vdeps_all_md)" in content
        assert "add_custom_target(vdeps_all_llvm_mt)" in content
        assert "add_custom_target(vdeps_all_llvm_md)" in content


class TestCmakeExecutionSimulation:
    """Test that generated CMake produces correct vdeps.py invocations."""

    def test_vdeps_py_receives_correct_dependency_names(self, tmp_path):
        """
        Test that when the generated CMake targets are executed,
        vdeps.py receives the ORIGINAL dependency names (from vdeps.toml),
        NOT the CMake target names.

        This is a critical bug: if a dependency is named 'vk-bootstrap',
        the CMake target is 'vdeps_vk_bootstrap', but vdeps.py needs
        to receive 'vk-bootstrap' (the original name from vdeps.toml).
        """
        write_config(
            tmp_path,
            """
[[dependency]]
name = "vk-bootstrap"
rel_path = "vk-bootstrap"
cmake_options = []

[[dependency]]
name = "SPIRV-Tools"
rel_path = "SPIRV-Tools"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)

        calls_made = []

        def capture_subprocess(call_args, **kwargs):
            """Capture any simulated subprocess calls."""
            calls_made.append(call_args)
            return type("obj", (object,), {"returncode": 0})()

        with patch("subprocess.run", side_effect=capture_subprocess):
            run_main(tmp_path, ["--generate-cmake"])

        vdeps_py_calls = [args[0] for args in calls_made if "vdeps.py" in str(args[0])]
        assert len(vdeps_py_calls) == 0, "Generating CMake shouldn't call vdeps.py"

        import re

        vdeps_build_dep_pattern = (
            r'vdeps_build_dep\s*\(\s*(\S+)\s+(\S+)\s+(\S+)\s+"([^"]*)"\)'
        )
        matches = re.findall(vdeps_build_dep_pattern, content)

        assert len(matches) > 0, "Should find vdeps_build_dep calls in generated CMake"

        for target_name, dep_name, suffix, extra_args in matches:
            assert dep_name == "vk-bootstrap" or dep_name == "SPIRV-Tools", (
                f"vdeps_build_dep should receive original dependency name "
                f"'vk-bootstrap' or 'SPIRV-Tools', but got '{dep_name}'. "
                f"CMake target was '{target_name}'."
            )

    def test_target_name_and_dep_name_are_separate(self, tmp_path):
        """
        Verify that the macro receives both target name and dependency name,
        and they are different for names with special characters.
        """
        write_config(
            tmp_path,
            """
[[dependency]]
name = "my-lib-123"
rel_path = "my-lib-123"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)

        import re

        vdeps_build_dep_pattern = (
            r'vdeps_build_dep\s*\(\s*(\S+)\s+(\S+)\s+(\S+)\s+"([^"]*)"\)'
        )
        matches = re.findall(vdeps_build_dep_pattern, content)

        assert len(matches) >= 1, "Should find at least one vdeps_build_dep call"

        target_name, dep_name, suffix, extra_args = matches[0]

        assert target_name == "vdeps_my_lib_123", (
            f"CMake target name should be 'vdeps_my_lib_123', got '{target_name}'"
        )
        assert dep_name == "my-lib-123", (
            f"Dependency name passed to vdeps.py should be 'my-lib-123', got '{dep_name}'"
        )
        assert target_name != dep_name, (
            "Target name and dependency name should be different"
        )

    def test_simulated_cmake_build_uses_correct_dep_names(self, tmp_path):
        """
        Simulate what happens when a user runs: cmake --build . --target vdeps_vk_bootstrap_mt

        The generated CMake should invoke:
            python vdeps.py --build --auto-skip "vk-bootstrap"

        NOT:
            python vdeps.py --build --auto-skip "vdeps_vk_bootstrap"
        """
        write_config(
            tmp_path,
            """
[[dependency]]
name = "vk-bootstrap"
rel_path = "vk-bootstrap"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)

        import re

        vdeps_build_dep_pattern = (
            r'vdeps_build_dep\s*\(\s*(\S+)\s+(\S+)\s+(\S+)\s+"([^"]*)"\)'
        )
        matches = re.findall(vdeps_build_dep_pattern, content)

        for target_name, dep_name, suffix, extra_args in matches:
            if target_name == "vdeps_vk_bootstrap" and suffix == "mt":
                assert dep_name == "vk-bootstrap", (
                    f"When building target 'vdeps_vk_bootstrap_mt', "
                    f"vdeps.py should receive dependency name 'vk-bootstrap', "
                    f"but got '{dep_name}'. This would cause: "
                    f"Error: Dependency '{dep_name}' not found in vdeps.toml"
                )

    def test_all_variants_pass_correct_dep_names(self, tmp_path):
        """
        Test that all runtime variants (mt, md, llvm_mt, llvm_md) all pass
        the correct dependency name to vdeps.py.
        """
        write_config(
            tmp_path,
            """
[[dependency]]
name = "test-dep"
rel_path = "test-dep"
cmake_options = []
""",
        )
        content = get_cmake_content(tmp_path)

        import re

        vdeps_build_dep_pattern = (
            r'vdeps_build_dep\s*\(\s*(\S+)\s+(\S+)\s+(\S+)\s+"([^"]*)"\)'
        )
        matches = re.findall(vdeps_build_dep_pattern, content)

        expected_variants = {
            ("vdeps_test_dep", "test-dep", "mt", ""),
            ("vdeps_test_dep", "test-dep", "llvm_mt", "--llvm"),
            ("vdeps_test_dep", "test-dep", "md", "--md"),
            ("vdeps_test_dep", "test-dep", "llvm_md", "--llvm --md"),
        }

        actual_variants = set(matches)

        for expected in expected_variants:
            assert expected in actual_variants, (
                f"Expected vdeps_build_dep call {expected} not found. "
                f"Available: {actual_variants}"
            )
