"""
Authentication and token management for the Copernicus Data Space Ecosystem (CDSE).
"""

import logging
import os
import threading
import time
from typing import Optional

import requests

from smart_sentinel.config import IDENTITY_URL, TOKEN_REFRESH_SECONDS

logger = logging.getLogger(__name__)


class CDSEAuthError(Exception):
    """Raised when authentication with CDSE fails."""


class AuthenticationManager:
    """
    Manages OAuth2 access tokens for CDSE API requests.
    Thread-safe with automatic token refresh.
    """

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.username = username or os.getenv("SENTINEL_USER")
        self.password = password or os.getenv("SENTINEL_PASS")
        self._token: Optional[str] = None
        self._token_timestamp: float = 0
        self._lock = threading.Lock()

    def get_token(self, force_refresh: bool = False) -> str:
        """
        Retrieves a valid bearer token, refreshing it automatically if expired or forced.
        """
        if not self.username or not self.password:
            raise CDSEAuthError(
                "Missing CDSE credentials. Set SENTINEL_USER and SENTINEL_PASS in your "
                ".env file or pass them directly to AuthenticationManager."
            )

        with self._lock:
            now = time.time()
            if not force_refresh and self._token and (now - self._token_timestamp < TOKEN_REFRESH_SECONDS):
                return self._token

            logger.debug("Requesting fresh CDSE authentication token...")
            try:
                response = requests.post(
                    IDENTITY_URL,
                    data={
                        "grant_type": "password",
                        "username": self.username,
                        "password": self.password,
                        "client_id": "cdse-public",
                    },
                    timeout=30,
                )

                if response.status_code == 401 or response.status_code == 400:
                    raise CDSEAuthError(
                        f"Authentication failed ({response.status_code}): Invalid username or password. "
                        "Please verify your credentials at https://dataspace.copernicus.eu/"
                    )

                response.raise_for_status()
                data = response.json()
                self._token = data.get("access_token")
                self._token_timestamp = time.time()

                if not self._token:
                    raise CDSEAuthError("Authentication response did not contain an access_token.")

                logger.debug("Successfully obtained CDSE authentication token.")
                return self._token

            except requests.exceptions.RequestException as exc:
                raise CDSEAuthError(f"Network error connecting to CDSE auth service: {exc}") from exc

    def test_connection(self) -> bool:
        """
        Verifies credentials by attempting to obtain a token.
        Returns True if successful, raises CDSEAuthError otherwise.
        """
        token = self.get_token(force_refresh=True)
        return bool(token)
