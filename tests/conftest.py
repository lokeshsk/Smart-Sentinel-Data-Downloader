"""
Pytest configuration and shared fixtures for mock CDSE services.
"""

import pytest

from smart_sentinel.auth import AuthenticationManager
from smart_sentinel.client import CDSEClient


@pytest.fixture
def mock_auth():
    """Provides an AuthenticationManager with mocked credentials and dummy token."""
    auth = AuthenticationManager(username="test_user@example.com", password="test_password")
    auth._token = "mock_access_token_12345"
    auth._token_timestamp = 9999999999.0
    return auth


@pytest.fixture
def mock_client(mock_auth):
    """Provides a CDSEClient bound to mock_auth."""
    return CDSEClient(auth_manager=mock_auth)
