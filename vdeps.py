#
#    -- Vdep --
#
#    Copyright 2026 UAA Software
#
#    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
#    associated documentation files (the "Software"), to deal in the Software without restriction,
#    including without limitation the rights to use, copy, modify, merge, publish, distribute,
#    sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
#    furnished to do so, subject to the following conditions:
#
#    The above copyright notice and this permission notice shall be included in all copies or substantial
#    portions of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
#    NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
#    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
#    OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
#    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import os
import subprocess
import shutil
import glob
import sys
import platform
import argparse

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# --- Configuration ---

CONFIGS = [{"name": "debug", "type": "Debug"}, {"name": "release", "type": "Release"}]

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

if IS_WINDOWS:
    PLATFORM_TAG = "win"
elif IS_MACOS:
    PLATFORM_TAG = "mac"
else:
    PLATFORM_TAG = "linux"

LIB_EXT = ".lib" if IS_WINDOWS else ".a"
VALID_PLATFORMS = {"win", "linux", "mac"}

# --- Helpers ---


# NOTE: Change these in the script here if these are not correct for your system
# (e.g. if you use a different compiler or build system)
#
def filter_platform_items(items):
    """
    Filters a list of items based on platform-specific prefix syntax.

    Supported syntax:
    - "platform:value" - only include if current platform matches
    - "!platform:value" - only include if current platform does NOT match
    - "platform1,platform2:value" - only include if current platform matches any
    - "value" - include on all platforms (backward compatible)

    Platform tags: win, linux, mac

    :param items: List of strings with optional platform prefixes
    :return: List of values that match the current platform
    """
    filtered = []

    for item in items:
        if ":" not in item:
            filtered.append(item)
            continue

        parts = item.split(":", 1)
        if len(parts) != 2:
            filtered.append(item)
            continue

        platform_spec, value = parts
        value = value.strip()  # Remove leading/trailing whitespace from value
        include = False

        if platform_spec.startswith("!"):
            exclude_platforms = [p.strip() for p in platform_spec[1:].split(",")]

            # Validate platform tags and warn about unknown ones
            warned = set()
            for platform in exclude_platforms:
                if platform not in VALID_PLATFORMS and platform not in warned:
                    print(f"Warning: Unknown platform tag '{platform}' in '{item}'")
                    warned.add(platform)

            if PLATFORM_TAG not in exclude_platforms:
                include = True
        else:
            include_platforms = [p.strip() for p in platform_spec.split(",")]

            # Validate platform tags and warn about unknown ones
            warned = set()
            for platform in include_platforms:
                if platform not in VALID_PLATFORMS and platform not in warned:
                    print(f"Warning: Unknown platform tag '{platform}' in '{item}'")
                    warned.add(platform)

            if PLATFORM_TAG in include_platforms:
                include = True

        if include:
            filtered.append(value)

    return filtered


def is_build_dir_valid(build_dir):
    """Check if build directory exists and contains CMake cache for building."""
    try:
        cmake_cache = os.path.join(build_dir, "CMakeCache.txt")
        return os.path.exists(build_dir) and os.path.exists(cmake_cache)
    except OSError:
        return False


def is_absolute_path(path):
    """Checks if a path is absolute, supporting both Unix and Windows styles."""
    if os.path.isabs(path):
        return True
    # Windows-style absolute path (e.g., C:\path or C:/path)
    if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
        return True
    return False


def get_platform_cmake_args(cxx_standard=20):
    """Returns CMake arguments specific to the current operating system."""
    common_args = [
        f"-DCMAKE_CXX_STANDARD={cxx_standard}",
        "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
    ]

    if IS_WINDOWS:
        # Windows-specific flags (MSVC default)
        return common_args + [
            "-DVK_USE_PLATFORM_WIN32_KHR=ON",
            # Enforce static runtime (MT/MTd)
            # This requires CMake 3.15+ and CMP0091 set to NEW
            "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>",
            # Turn off all warnings
            "-DCMAKE_C_FLAGS=/W0",
            "-DCMAKE_CXX_FLAGS=/W0 /EHsc",
        ]
    else:
        # Unix-like flags (Clang + Ninja + libc++)
        args = common_args + [
            "-G",
            "Ninja",
            "-DCMAKE_C_COMPILER=clang",
            "-DCMAKE_CXX_COMPILER=clang++",
            "-DCMAKE_C_FLAGS=-w",
            "-DCMAKE_CXX_FLAGS=-w -stdlib=libc++",
        ]

        # Linker flags: macOS libc++ includes abi, Linux often needs explicit -lc++abi
        link_flags = "-stdlib=libc++"
        if not IS_MACOS:
            link_flags += " -lc++abi"

        args.append(f"-DCMAKE_EXE_LINKER_FLAGS={link_flags}")
        args.append(f"-DCMAKE_SHARED_LINKER_FLAGS={link_flags}")

        return args


def run_command(command, cwd=None, env=None):
    """Executes a shell command and exits on failure."""
    cwd_path = cwd or os.getcwd()
    print(f"[{cwd_path}] Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, env=env, shell=False)
    if result.returncode != 0:
        print(f"Error: Command failed with return code {result.returncode}")
        sys.exit(1)


class Dependency:
    def __init__(
        self,
        name,
        rel_path,
        cmake_options,
        libs=None,
        executables=None,
        extra_files=None,
        extra_link_dirs=None,
        cxx_standard=20,
    ):
        """
        :param name: Display name.
        :param rel_path: Relative path from 'dependencies/'.
        :param cmake_options: List of dependency-specific CMake flags.
        :param libs: List of library base names to copy (e.g. ['nvrhi']).
                     Matches 'libnvrhi.a' (Linux) or 'nvrhi.lib'/'libnvrhi.lib' (Windows).
                     If None, copies all static libs found.
        :param executables: List of executable base names to copy (e.g. ['nvrhi-scomp']).
                            Matches 'nvrhi-scomp' (Linux) or 'nvrhi-scomp.exe' (Windows).
        :param extra_files: List of specific filenames to find and copy to the tools directory (e.g. ['slangc.exe', 'slang.dll']).

        :param extra_link_dirs: List of additional paths to add to linker search paths for this dependency.
        :param cxx_standard: C++ standard version (e.g. 17, 20, 23). Default is 20.
        """
        self.name = name
        self.rel_path = rel_path
        self.cmake_options = cmake_options
        self.libs = libs
        self.executables = executables
        self.extra_files = extra_files

        self.extra_link_dirs = extra_link_dirs or []
        self.cxx_standard = cxx_standard


# --- Main Build Logic ---


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    deps_root_dir = os.path.join(root_dir, "vdeps")
    env = os.environ.copy()

    print(f"Platform: {sys.platform} ({PLATFORM_TAG})")

    parser = argparse.ArgumentParser(description="Build CMake dependencies")
    parser.add_argument(
        "--build",
        action="store_true",
        help="Only build without regenerating project (requires existing build directories)",
    )
    args, _ = parser.parse_known_args()

    # Load Dependencies from TOML
    toml_path = os.path.join(root_dir, "vdeps.toml")
    if not os.path.exists(toml_path):
        print(f"Error: Configuration file not found at {toml_path}")
        sys.exit(1)

    try:
        with open(toml_path, "rb") as f:
            toml_data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"Error parsing TOML file: {e}")
        sys.exit(1)

    dependencies = []
    for dep_data in toml_data.get("dependency", []):
        try:
            dependencies.append(Dependency(**dep_data))
        except TypeError as e:
            print(f"Error initializing dependency from TOML data: {dep_data}")
            print(f"Details: {e}")
            sys.exit(1)

    temp_dir = toml_data.get("temp_dir", None)

    for dep in dependencies:
        dep_dir = os.path.join(deps_root_dir, dep.rel_path)

        if not os.path.exists(dep_dir):
            print(f"Error: Directory for {dep.name} not found at {dep_dir}")
            continue

        print(f"\n=== Processing Dependency: {dep.name} ===")

        # Apply platform filtering to arrays
        dep.cmake_options = filter_platform_items(dep.cmake_options or [])
        dep.libs = filter_platform_items(dep.libs or []) if dep.libs else None
        dep.executables = (
            filter_platform_items(dep.executables or []) if dep.executables else None
        )
        dep.extra_files = (
            filter_platform_items(dep.extra_files or []) if dep.extra_files else None
        )

        for config in CONFIGS:
            # Determine actual CMake build type
            # On Windows, we want RelWithDebInfo instead of Release to get PDBs
            build_type = config["type"]
            if IS_WINDOWS and config["name"] == "release":
                build_type = "RelWithDebInfo"

            print(f"\n--- Building {dep.name} [{build_type}] ---")

            if temp_dir and temp_dir.strip():
                build_dir = os.path.join(
                    root_dir, temp_dir.strip(), f"{dep.name}_{config['name']}"
                )
                # Ensure temp_dir parent directory exists
                os.makedirs(os.path.dirname(build_dir), exist_ok=True)
            else:
                build_dir = os.path.join(dep_dir, f"build_{config['name']}")
            output_lib_dir = os.path.join(
                root_dir, "lib", f"{PLATFORM_TAG}_{config['name']}"
            )
            output_tools_dir = os.path.join(
                root_dir, "tools", f"{PLATFORM_TAG}_{config['name']}"
            )

            if not os.path.exists(output_lib_dir):
                os.makedirs(output_lib_dir)

            if (dep.executables or dep.extra_files) and not os.path.exists(
                output_tools_dir
            ):
                os.makedirs(output_tools_dir)

            # Environment Setup
            build_env = env.copy()

            # CMake Configure
            cmake_args = (
                ["cmake", "-S", ".", "-B", build_dir]
                + get_platform_cmake_args(cxx_standard=dep.cxx_standard)
                + [f"-DCMAKE_BUILD_TYPE={build_type}"]
                + dep.cmake_options
            )

            # Resolve library paths for Linker Flags (Bypassing MSBuild env sanitization)
            link_dirs_abs = [output_lib_dir]
            for p in dep.extra_link_dirs:
                if is_absolute_path(p):
                    link_dirs_abs.append(p)
                else:
                    link_dirs_abs.append(os.path.join(root_dir, p))

            if link_dirs_abs:
                if IS_WINDOWS:
                    # Windows (MSVC)
                    path_flags = [f'/LIBPATH:"{p}"' for p in link_dirs_abs]
                    flags_str = " ".join(path_flags)
                else:
                    # Linux/macOS
                    path_flags = [f'-L"{p}"' for p in link_dirs_abs]
                    flags_str = " ".join(path_flags)

                # Append to existing linker flags if present, or add new ones
                def update_flag(args, flag_name, new_val):
                    found = False
                    for i, arg in enumerate(args):
                        if arg.startswith(f"{flag_name}="):
                            args[i] = f"{arg} {new_val}"
                            found = True
                    if not found:
                        args.append(f"{flag_name}={new_val}")

                update_flag(cmake_args, "-DCMAKE_EXE_LINKER_FLAGS", flags_str)
                update_flag(cmake_args, "-DCMAKE_SHARED_LINKER_FLAGS", flags_str)

            # Check if we should skip configure (only run build)
            if args.build and is_build_dir_valid(build_dir):
                print(f"--- Skipping CMake configure for {dep.name} [{build_type}] ---")
            else:
                # Run configure (either not in --build mode or build dir doesn't exist)
                if args.build:
                    print(
                        f"Warning: Build directory not valid at {build_dir}, running configure anyway..."
                    )
                run_command(cmake_args, cwd=dep_dir, env=build_env)

            # CMake Build
            # For Multi-Config generators (like VS), we must specify --config
            build_cmd = ["cmake", "--build", build_dir]
            if IS_WINDOWS:
                build_cmd.extend(["--config", build_type])

            run_command(build_cmd, cwd=dep_dir, env=build_env)

            # Copy Artifacts (Libs)
            print(f"--- Copying artefacts to {output_lib_dir} ---")

            # Find all relevant files in build dir
            extensions = [LIB_EXT, ".dylib", ".so"]
            if IS_WINDOWS:
                extensions.append(".pdb")
                extensions.append(".dll")

            found_files = glob.glob(os.path.join(build_dir, "**", "*"), recursive=True)

            # Also search in the 'bin' and 'lib' directories of the dependency if they exist (e.g. Slang)
            bin_dir = os.path.join(dep_dir, "bin")
            if os.path.exists(bin_dir):
                found_files.extend(
                    glob.glob(os.path.join(bin_dir, "**", "*"), recursive=True)
                )

            lib_dir = os.path.join(dep_dir, "lib")
            if os.path.exists(lib_dir):
                found_files.extend(
                    glob.glob(os.path.join(lib_dir, "**", "*"), recursive=True)
                )

            copied_count = 0

            for file_path in found_files:
                if os.path.isdir(file_path):
                    continue
                filename = os.path.basename(file_path)
                name_no_ext = os.path.splitext(filename)[0]
                ext = os.path.splitext(filename)[1]

                # --- Libs ---
                should_copy_lib = False
                
                is_lib_artifact = False
                if ext in extensions:
                    is_lib_artifact = True
                elif not IS_WINDOWS:
                    # Handle versioned shared libraries on Linux/Mac (e.g. .so.1 or .1.dylib)
                    if ".so." in filename or (".dylib" in filename and filename.endswith(ext) and ext != ".dylib"):
                        is_lib_artifact = True

                if is_lib_artifact:
                    if dep.libs is None:
                        should_copy_lib = True
                    else:
                        for base_name in dep.libs:
                            if (
                                name_no_ext == base_name
                                or name_no_ext == f"lib{base_name}"
                                or filename.startswith(f"lib{base_name}.so")
                                or filename.startswith(f"{base_name}.so")
                            ):
                                should_copy_lib = True
                                break

                if should_copy_lib:
                    print(f"Copying lib {filename}...")
                    shutil.copy2(file_path, os.path.join(output_lib_dir, filename))
                    copied_count += 1

                # --- Executables ---
                if dep.executables:
                    should_copy_exe = False
                    exe_ext = ".exe" if IS_WINDOWS else ""

                    if ext == exe_ext or (IS_WINDOWS and ext == ".pdb"):
                        # Check against executable names
                        # For PDBs on windows, we match the basename of the exe
                        for base_name in dep.executables:
                            if name_no_ext == base_name:
                                should_copy_exe = True
                                break

                    # On Linux, executables have no extension, so we check name match and executable permission (implied by being a build artifact usually, but name match is key)
                    # If extension is empty and we are not on windows, match exact name
                    if not IS_WINDOWS and ext == "":
                        for base_name in dep.executables:
                            if filename == base_name:
                                should_copy_exe = True
                                break

                    if should_copy_exe:
                        print(f"Copying tool {filename}...")
                        shutil.copy2(
                            file_path, os.path.join(output_tools_dir, filename)
                        )
                        copied_count += 1

                # --- Extra Files ---
                if dep.extra_files:
                    if filename in dep.extra_files:
                        print(f"Copying extra file {filename} to tools...")
                        shutil.copy2(
                            file_path, os.path.join(output_tools_dir, filename)
                        )
                        copied_count += 1

            if copied_count == 0:
                print(f"Warning: No artifacts copied for {dep.name} [{config['type']}]")

    if args.build:
        print("\n[SUCCESS] All dependencies built (configure skipped where possible).")
    else:
        print("\n[SUCCESS] All dependencies processed.")


if __name__ == "__main__":
    main()
