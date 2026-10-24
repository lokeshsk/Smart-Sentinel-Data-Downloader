"""
Unit tests for CDSE AuthenticationManager.
"""

import pytest
import responses

from smart_sentinel.auth import AuthenticationManager, CDSEAuthError
from smart_sentinel.config import IDENTITY_URL


def test_missing_credentials():
    """Verify error raised when credentials are not supplied."""
    auth = AuthenticationManager(username=None, password=None)
    with pytest.raises(CDSEAuthError, match="Missing CDSE credentials"):
        auth.get_token()


@responses.activate
def test_successful_token_acquisition():
    """Verify token is retrieved and cached properly."""
    responses.add(
        responses.POST,
        IDENTITY_URL,
        json={"access_token": "fresh_test_token_abc"},
        status=200,
    )

    auth = AuthenticationManager(username="user@example.com", password="password")
    token = auth.get_token()

    assert token == "fresh_test_token_abc"
    assert auth._token == "fresh_test_token_abc"
    assert len(responses.calls) == 1

    # Second call should use cached token without additional request
    cached_token = auth.get_token()
    assert cached_token == "fresh_test_token_abc"
    assert len(responses.calls) == 1


@responses.activate
def test_invalid_credentials_raises_error():
    """Verify 401 returns clear CDSEAuthError."""
    responses.add(
        responses.POST,
        IDENTITY_URL,
        status=401,
        json={"error": "invalid_grant", "error_description": "Invalid user credentials"},
    )

    auth = AuthenticationManager(username="bad_user@example.com", password="wrong_password")
    with pytest.raises(CDSEAuthError, match="Invalid username or password"):
        auth.get_token()


@responses.activate
def test_token_force_refresh():
    """Verify force_refresh triggers new network request."""
    responses.add(
        responses.POST,
        IDENTITY_URL,
        json={"access_token": "token_1"},
        status=200,
    )
    responses.add(
        responses.POST,
        IDENTITY_URL,
        json={"access_token": "token_2"},
        status=200,
    )

    auth = AuthenticationManager(username="user@example.com", password="password")
    t1 = auth.get_token()
    assert t1 == "token_1"

    t2 = auth.get_token(force_refresh=True)
    assert t2 == "token_2"
    assert len(responses.calls) == 2
