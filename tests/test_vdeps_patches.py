import sys
import os
import tempfile
import pytest
from unittest.mock import patch

# Add project root to path so we can import vdeps
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vdeps


def test_apply_and_revert_basic_patch():
    """Test basic patch apply and revert functionality."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("hello world")
        temp_file = f.name

    try:
        # Define a patch
        patch = {
            "file": os.path.basename(temp_file),
            "search": "hello",
            "replace": "hi",
        }

        # Apply patch
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])

        # Verify patch was applied
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "hi world"

        # Revert patch
        vdeps.revert_patches(os.path.dirname(temp_file), [patch])

        # Verify patch was reverted
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "hello world"
    finally:
        os.unlink(temp_file)


def test_apply_patch_search_not_found():
    """Test applying patch when search string is not found."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("hello world")
        temp_file = f.name

    try:
        # Define a patch with search string not in file
        patch = {"file": os.path.basename(temp_file), "search": "xyz", "replace": "abc"}

        # Apply patch (should warn but not crash)
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])

        # Verify file unchanged
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "hello world"
    finally:
        os.unlink(temp_file)


def test_apply_patch_file_not_found():
    """Test applying patch to non-existent file."""
    # Define a patch for non-existent file
    patch = {"file": "nonexistent.txt", "search": "hello", "replace": "hi"}

    # Apply patch (should warn but not crash)
    vdeps.apply_patches("/tmp", [patch])


def test_multiple_patches_different_files():
    """Test applying multiple patches to different files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create two test files
        file1_path = os.path.join(temp_dir, "file1.txt")
        file2_path = os.path.join(temp_dir, "file2.txt")

        with open(file1_path, "w", encoding="utf-8") as f:
            f.write("hello world")
        with open(file2_path, "w", encoding="utf-8") as f:
            f.write("foo bar")

        # Define patches
        patch1 = {"file": "file1.txt", "search": "hello", "replace": "hi"}
        patch2 = {"file": "file2.txt", "search": "foo", "replace": "baz"}

        # Apply patches
        vdeps.apply_patches(temp_dir, [patch1, patch2])

        # Verify patches applied
        with open(file1_path, "r", encoding="utf-8") as f:
            content1 = f.read()
        with open(file2_path, "r", encoding="utf-8") as f:
            content2 = f.read()
        assert content1 == "hi world"
        assert content2 == "baz bar"

        # Revert patches
        vdeps.revert_patches(temp_dir, [patch1, patch2])

        # Verify patches reverted
        with open(file1_path, "r", encoding="utf-8") as f:
            content1 = f.read()
        with open(file2_path, "r", encoding="utf-8") as f:
            content2 = f.read()
        assert content1 == "hello world"
        assert content2 == "foo bar"


def test_chained_patch_revert_order():
    """Test that chained patches are correctly reverted in reverse order.

    This test verifies that when multiple patches modify the same file in sequence,
    reverting them restores the original content correctly.
    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("aaa bbb")
        temp_file = f.name

    try:
        # Define chained patches:
        # Patch 1: "aaa" -> "xxx"
        # Patch 2: "xxx bbb" -> "yyy"
        patch1 = {
            "file": os.path.basename(temp_file),
            "search": "aaa",
            "replace": "xxx",
        }
        patch2 = {
            "file": os.path.basename(temp_file),
            "search": "xxx bbb",
            "replace": "yyy",
        }

        # Apply patches in order
        vdeps.apply_patches(os.path.dirname(temp_file), [patch1, patch2])

        # Verify both patches applied
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "yyy", f"Expected 'yyy' after both patches, got '{content}'"

        # Revert patches using the current implementation
        # The correct behavior should revert in REVERSE order (last applied, first reverted)
        vdeps.revert_patches(os.path.dirname(temp_file), [patch1, patch2])

        # Verify content is restored to original
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()

        # This assertion will FAIL with buggy code (reverts in forward order)
        # and PASS with fixed code (reverts in reverse order)
        assert content == "aaa bbb", (
            f"Expected 'aaa bbb' after reverting patches, got '{content}'. "
            "This failure indicates patches are not being reverted in the correct order."
        )
    finally:
        os.unlink(temp_file)


def test_patch_with_multiple_occurrences():
    """Test patch where search string appears multiple times."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("foo bar foo baz foo")
        temp_file = f.name

    try:
        # Define patch that should only replace first occurrence
        patch = {"file": os.path.basename(temp_file), "search": "foo", "replace": "qux"}

        # Apply patch
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])

        # Verify only first occurrence replaced
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "qux bar foo baz foo"

        # Revert patch
        vdeps.revert_patches(os.path.dirname(temp_file), [patch])

        # Verify patch reverted
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "foo bar foo baz foo"
    finally:
        os.unlink(temp_file)


def test_patch_replace_already_exists_in_content():
    """Test patch where replace string already exists in original content."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("hello world hello")
        temp_file = f.name

    try:
        # Define patch where replace string already exists
        patch = {
            "file": os.path.basename(temp_file),
            "search": "hello",
            "replace": "world",
        }

        # Apply patch
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])

        # Verify patch applied (only first occurrence replaced)
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "world world hello"

        # Revert patch
        vdeps.revert_patches(os.path.dirname(temp_file), [patch])

        # Verify patch reverted
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "hello world hello"
    finally:
        os.unlink(temp_file)


def test_empty_file_patch():
    """Test applying patch to empty file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        temp_file = f.name  # File is empty

    try:
        # Define patch
        patch = {
            "file": os.path.basename(temp_file),
            "search": "hello",
            "replace": "hi",
        }

        # Apply patch (should warn but not crash)
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])

        # Verify file still empty
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == ""
    finally:
        os.unlink(temp_file)


def test_three_chained_patches():
    """Test three patches in sequence - verifies reverse order works for n>2."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("aaa")
        temp_file = f.name

    try:
        # Three chained patches
        patch1 = {
            "file": os.path.basename(temp_file),
            "search": "aaa",
            "replace": "bbb",
        }
        patch2 = {
            "file": os.path.basename(temp_file),
            "search": "bbb",
            "replace": "ccc",
        }
        patch3 = {
            "file": os.path.basename(temp_file),
            "search": "ccc",
            "replace": "ddd",
        }

        # Apply all three
        vdeps.apply_patches(os.path.dirname(temp_file), [patch1, patch2, patch3])

        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "ddd"

        # Revert all three
        vdeps.revert_patches(os.path.dirname(temp_file), [patch1, patch2, patch3])

        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "aaa"
    finally:
        os.unlink(temp_file)


def test_patch_idempotency():
    """Test that applying a patch twice doesn't break, and reverting twice works."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("hello world")
        temp_file = f.name

    try:
        patch = {
            "file": os.path.basename(temp_file),
            "search": "hello",
            "replace": "hi",
        }

        # Apply once
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hi world"

        # Apply again - should warn (search not found)
        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hi world"  # Still same

        # Revert once
        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hello world"

        # Revert again - should not corrupt
        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hello world"
    finally:
        os.unlink(temp_file)


def test_multiline_patch():
    """Test patches that span multiple lines."""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, encoding="utf-8", newline=""
    ) as f:
        f.write("line1\nOLD_CONTENT\nline3")
        temp_file = f.name

    try:
        patch = {
            "file": os.path.basename(temp_file),
            "search": "line1\nOLD_CONTENT\nline3",
            "replace": "line1\nNEW_CONTENT\nline3",
        }

        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8", newline="") as f:
            assert f.read() == "line1\nNEW_CONTENT\nline3"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8", newline="") as f:
            assert f.read() == "line1\nOLD_CONTENT\nline3"
    finally:
        os.unlink(temp_file)


def test_patch_special_characters():
    """Test patches with special regex-like characters."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("hello (world) [test] {foo}")
        temp_file = f.name

    try:
        patch = {
            "file": os.path.basename(temp_file),
            "search": "(world)",
            "replace": "(universe)",
        }

        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hello (universe) [test] {foo}"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hello (world) [test] {foo}"
    finally:
        os.unlink(temp_file)


def test_patch_adjacent_content():
    """Test patches that modify adjacent content in file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("AAAAbbbbCCCC")
        temp_file = f.name

    try:
        # Patch 1: modify middle of string
        patch1 = {
            "file": os.path.basename(temp_file),
            "search": "bbbb",
            "replace": "BBBB",
        }
        # Patch 2: modify after patch1 result
        patch2 = {
            "file": os.path.basename(temp_file),
            "search": "BBBBCCCC",
            "replace": "bbbbDDDD",
        }

        vdeps.apply_patches(os.path.dirname(temp_file), [patch1, patch2])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "AAAAbbbbDDDD"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch1, patch2])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "AAAAbbbbCCCC"
    finally:
        os.unlink(temp_file)


def test_patch_non_utf8_binary():
    """Test patches work with binary-like content."""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        f.write(b"hello\x00world\x00")
        temp_file = f.name

    try:
        patch = {
            "file": os.path.basename(temp_file),
            "search": "hello\x00",
            "replace": "hi\x00",
        }

        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "rb") as f:
            assert f.read() == b"hi\x00world\x00"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "rb") as f:
            assert f.read() == b"hello\x00world\x00"
    finally:
        os.unlink(temp_file)


def test_patch_overlapping_regions():
    """Test patches that modify overlapping regions - order matters."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("abcdefghij")
        temp_file = f.name

    try:
        # These patches modify overlapping regions
        patch1 = {
            "file": os.path.basename(temp_file),
            "search": "abc",
            "replace": "XYZ",
        }
        patch2 = {
            "file": os.path.basename(temp_file),
            "search": "XYZdef",
            "replace": "UVW",
        }

        vdeps.apply_patches(os.path.dirname(temp_file), [patch1, patch2])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "UVWghij"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch1, patch2])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "abcdefghij"
    finally:
        os.unlink(temp_file)


def test_patch_unicode_content():
    """Test patches with unicode characters."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("hello 世界 🌍")
        temp_file = f.name

    try:
        patch = {
            "file": os.path.basename(temp_file),
            "search": "世界",
            "replace": "宇宙",
        }

        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hello 宇宙 🌍"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "hello 世界 🌍"
    finally:
        os.unlink(temp_file)


def test_patch_single_character():
    """Test patching a single character."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("abc")
        temp_file = f.name

    try:
        patch = {"file": os.path.basename(temp_file), "search": "a", "replace": "x"}

        vdeps.apply_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "xbc"

        vdeps.revert_patches(os.path.dirname(temp_file), [patch])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "abc"
    finally:
        os.unlink(temp_file)


def test_patch_no_match_after_partial_revert():
    """Test scenario where intermediate revert doesn't find its match."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("start MIDDLE end")
        temp_file = f.name

    try:
        # First patch
        patch1 = {
            "file": os.path.basename(temp_file),
            "search": "start",
            "replace": "BEGIN",
        }
        # Second patch modifies the result of first
        patch2 = {
            "file": os.path.basename(temp_file),
            "search": "BEGIN MIDDLE",
            "replace": "FINAL",
        }

        # Apply
        vdeps.apply_patches(os.path.dirname(temp_file), [patch1, patch2])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "FINAL end"

        # Revert - with correct reverse order, should work
        vdeps.revert_patches(os.path.dirname(temp_file), [patch1, patch2])
        with open(temp_file, "r", encoding="utf-8") as f:
            assert f.read() == "start MIDDLE end"
    finally:
        os.unlink(temp_file)


if __name__ == "__main__":
    pytest.main([__file__])
