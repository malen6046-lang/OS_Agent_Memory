"""Test client and import-path fixtures."""

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from tests.asgi_client import ASGITestClient


@pytest.fixture
def client():
    with ASGITestClient(app, raise_app_exceptions=False) as test_client:
        yield test_client
