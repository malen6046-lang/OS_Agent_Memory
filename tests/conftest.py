import pytest

from app.main import app
from tests.asgi_client import ASGITestClient


@pytest.fixture
def client() -> ASGITestClient:
    with ASGITestClient(app, raise_app_exceptions=False) as test_client:
        yield test_client
