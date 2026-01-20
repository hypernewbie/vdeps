import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def clean_argv():
    """Isolate tests from pytest's sys.argv pollution."""
    with patch('sys.argv', ['vdeps.py']):
        yield
