#!/usr/bin/env python3
"""
Generate dummy build artefacts for vdeps testing.
Creates library and executable files with appropriate headers.
"""

import sys
import os
import argparse


def create_library_file(filepath, basename, is_windows=False):
    """Create a static library file with appropriate header."""
    # Create directory if needed
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    if is_windows:
        # MSVC static library magic: "!<arch>\n" format (same as Unix actually)
        header = b"!<arch>\n"
        # Add a simple symbol table entry
        content = header + f"{basename}.obj/\n".encode()
    else:
        # Unix static library: ar format
        header = b"!<arch>\n"
        # Add a simple symbol table entry
        content = header + f"{basename}.o/\n".encode()
    
    with open(filepath, 'wb') as f:
        f.write(content)
    
    # Make Unix libs non-executable, Windows libs don't need special perms
    if not is_windows:
        os.chmod(filepath, 0o644)
    
    print(f"Created library: {filepath}")


def create_executable_file(filepath, basename, is_windows=False):
    """Create an executable file with appropriate header."""
    # Create directory if needed
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    if is_windows:
        # PE (Portable Executable) header - simplified version
        # Magic number: MZ
        header = b"MZ\x90\x00\x03\x00\x00\x00"
        content = header + f"This is {basename}.exe".encode()
    else:
        # ELF header - simplified version
        header = b"\x7fELF\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        content = header + f"This is {basename}".encode()
    
    with open(filepath, 'wb') as f:
        f.write(content)
    
    # Make Unix executables... executable
    if not is_windows:
        os.chmod(filepath, 0o755)
    
    print(f"Created executable: {filepath}")


def create_extra_file(filepath, filename):
    """Create an arbitrary extra file (e.g., data.blob)."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    content = f"Dummy data file: {filename}\n".encode()
    with open(filepath, 'wb') as f:
        f.write(content)
    
    print(f"Created extra file: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Generate dummy build artefacts")
    parser.add_argument("type", choices=["lib", "exe", "extra"], help="Type of artefact to create")
    parser.add_argument("basename", help="Base name without extension")
    parser.add_argument("extension", help="File extension (e.g., .a, .lib, .exe)")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--platform", choices=["linux", "win", "mac"], default="linux", help="Platform")
    
    args = parser.parse_args()
    
    # Determine if this is a Windows-style build
    is_windows = args.platform == "win"
    
    # Handle Unix library naming convention (add 'lib' prefix if not Windows)
    if args.type == "lib" and not is_windows and not args.basename.startswith("lib"):
        filename = f"lib{args.basename}{args.extension}"
    else:
        filename = f"{args.basename}{args.extension}"
    
    filepath = os.path.join(args.output_dir, filename)
    
    try:
        if args.type == "lib":
            create_library_file(filepath, args.basename, is_windows)
        elif args.type == "exe":
            create_executable_file(filepath, args.basename, is_windows)
        elif args.type == "extra":
            create_extra_file(filepath, args.basename)
        
        return 0
    except Exception as e:
        print(f"Error creating artefact: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
