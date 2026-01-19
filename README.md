# Vdeps - Simple dependency compiler for CMake

[![build](https://github.com/hypernewbie/vdeps/actions/workflows/ci.yml/badge.svg)](https://github.com/hypernewbie/vdeps/actions/workflows/ci.yml)

Vdeps is a lightweight Python script that compiles cmake dependencies for you. This is great if you just went to compile them in a separate directory without dealing with the fun task
of trying to link the cmakes builds together directly. In the end you just want to build some libraries and copy them into a folder for your project to link, right?

> NOTE: Vdeps is vibe coded, without too much code oversight. Intended as a throwaway tool of sorts. Use at your own risk.

## Overview

`vdeps.py` builds dependency libraries and tools defined in `vdeps.toml`, copying artefacts to `lib/` and `tools/` directories organised by platform and build configuration.

## Usage

```bash
# Run the dependency build script
python vdeps.py

# Only build (skip project regeneration if build exists)
python vdeps.py --build
```

## Configuration

Dependencies are configured in `vdeps.toml`:

```toml
# Optional: centralise build artefacts
temp_dir = "builds"

[[dependency]]
name = "nvrhi"
rel_path = "nvrhi"
cxx_standard = 20
libs = ["nvrhi_vk", "rtxmu", "nvrhi"]
executables = []
cmake_options = [
    "-DNVRHI_INSTALL=OFF",
    "win:-DNVRHI_WITH_DX11=OFF",
    "linux,mac:-DNVRHI_WITH_VULKAN=ON",
    "!win:-DNOT_WINDOWS=ON",
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
| `cmake_options` | List of CMake flags passed during configuration |
| `cxx_standard` | C++ standard version (default: 20) |
| `extra_link_dirs` | Additional linker search paths for this dependency |

**Platform-specific syntax:** Use `win:`, `linux:`, `mac:` prefixes for platform-specific items in arrays. Negation with `!` and multiple platforms with commas: `"win,linux:-DFEATURE=ON"`, `"!win:-DNOT_WIN=ON"`.

**Centralised builds:** Add `temp_dir = "builds"` at top-level to redirect build directories from `{dependency}/build_{config}` to `{temp_dir}/{name}_{config}`.

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

## Platform-Specific Behaviour

### Linux/macOS
- Generator: Ninja
- Compiler: Clang/Clang++
- Library extension: `.a`
- Executable extension: none
- Warning suppression: `-w` (can be overridden via `cmake_options`)

### Windows
- Generator: Visual Studio (MultiConfig)
- Compiler: MSVC
- Library extension: `.lib`
- Executable extension: `.exe`
- Release builds use `RelWithDebInfo` for PDB files
- Warning suppression: `/W0` (can be overridden via `cmake_options`)

## Testing

```bash
# Run all tests
./venv/bin/python -m pytest tests/ -v

# Or with coverage
./venv/bin/python -m pytest tests/ -v --cov=vdeps
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
