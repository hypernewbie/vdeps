# Vdeps - Simple dependency compiler for CMake

Vdeps is a lightweight Python script that compiles cmake dependencies for you. This is great if you just went to compile them in a separate directory without dealing with the fun task
of trying to link the cmakes builds together directly. In the end you just want to build some libraries and copy them into a folder for your project to link, right?

> NOTE: Vdeps is vibe coded, without too much code oversight. Intended as a throwaway tool of sorts. Use at your own risk.

## Overview

`vdeps.py` builds dependency libraries and tools defined in `vdeps.toml`, copying artifacts to `lib/` and `tools/` directories organized by platform and build configuration.

## Usage

```bash
# Run the dependency build script
python vdeps.py
```

## Configuration

Dependencies are configured in `vdeps.toml`:

```toml
[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
init_submodules = true
libs = ["nvrhi_vk", "rtxmu", "nvrhi"]
executables = []
cmake_options = [
    "-DNVRHI_INSTALL=OFF",
    "-DNVRHI_WITH_VULKAN=ON",
]
```

### Dependency Options

| Field | Description |
|-------|-------------|
| `name` | Display name for logging |
| `rel_path` | Relative path to dependency in `vdeps/` directory |
| `libs` | Library base names to copy (e.g. `["nvrhi"]` matches `libnvrhi.a` or `nvrhi.lib`) |
| `executables` | Executable base names to copy to tools directory |
| `extra_files` | Specific filenames to copy (e.g. `["slangc.exe", "slang.dll"]`) |
| `init_submodules` | Whether to initialize git submodules |
| `cmake_options` | List of CMake flags passed during configuration |

## Output Structure

```
root/
├── vdeps.py
├── vdeps.toml
├── lib/
│   ├── linux_debug/
│   ├── linux_release/
│   ├── win_debug/
│   └── win_release/
└── tools/
    ├── linux_debug/
    ├── linux_release/
    ├── win_debug/
    └── win_release/
```

## Platform-Specific Behavior

### Linux/macOS
- Generator: Ninja
- Compiler: Clang/Clang++
- Library extension: `.a`
- Executable extension: none

### Windows
- Generator: Visual Studio (MultiConfig)
- Compiler: MSVC
- Library extension: `.lib`
- Executable extension: `.exe`
- Release builds use `RelWithDebInfo` for PDB files

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Or with coverage
python -m pytest tests/ -v --cov=vdeps
```

The test suite uses functional CMake projects with a Python artefact generator (`tests/fixtures/vdeps/gen_artifact.py`). These mock projects build quickly and test platform-specific behaviour, error handling, and configuration options without requiring actual C++ compilation.

To run specific test categories:
```bash
# Platform-specific tests only
./venv/bin/python -m pytest tests/test_vdeps_platforms.py -v

# Configuration tests
./venv/bin/python -m pytest tests/test_vdeps_configuration.py -v
```

## Requirements

- Python 3.10+
- CMake 3.15+
- Ninja (Linux/macOS)
- Visual Studio 2019+ (Windows)

## License

Vdeps is released under the MIT license:

```
    Copyright 2026 UAA Software

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
    associated documentation files (the "Software"), to deal in the Software without restriction,
    including without limitation the rights to use, copy, modify, merge, publish, distribute,
    sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial
    portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
    NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
    OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
