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
        assert 'vdeps_build_dep(vdeps_nvrhi mt "")' in content
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
        assert 'vdeps_build_dep(vdeps_nvrhi mt "")' in content


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
        assert 'vdeps_build_dep(vdeps_nvrhi md "--md")' in content


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
        assert 'vdeps_build_dep(vdeps_nvrhi mt "")' in content
        assert 'vdeps_build_dep(vdeps_nvrhi md "--md")' in content

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
        assert 'vdeps_build_dep(vdeps_nvrhi llvm_mt "--llvm")' in content

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
        assert 'vdeps_build_dep(vdeps_nvrhi llvm_md "--llvm --md")' in content

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
        assert 'vdeps_build_dep(vdeps_nvrhi llvm_mt "--llvm")' in content
        assert 'vdeps_build_dep(vdeps_nvrhi llvm_md "--llvm --md")' in content


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
