"""Shared OAuth credential handling for Google APIs used by the Career app."""

import json
from json import JSONDecodeError
from pathlib import Path

from django.conf import settings
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GoogleAuthError(RuntimeError):
    """Base error for Google OAuth credential failures."""


class GoogleCredentialsNotFoundError(GoogleAuthError):
    """The local OAuth client credentials file is unavailable."""


class GoogleTokenError(GoogleAuthError):
    """The saved Google OAuth token cannot be used."""


class GoogleInsufficientScopesError(GoogleAuthError):
    """The authorized Google token does not grant all required scopes."""


def credential_paths():
    """Return the project-local OAuth client and user-token file paths."""
    base_dir = Path(settings.BASE_DIR)
    return base_dir / "credentials.json", base_dir / "token.json"


def _scope_set(scopes):
    if isinstance(scopes, str):
        return set(scopes.split())
    return set(scopes or [])


def _token_scopes(token_path):
    try:
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as error:
        raise GoogleTokenError(
            f"Google token at {token_path} is invalid. Delete it and authorize again."
        ) from error
    return _scope_set(token_data.get("scopes"))


def _missing_scopes(scopes):
    return set(SCOPES) - _scope_set(scopes)


def _authorized_scopes(credentials):
    return _scope_set(
        getattr(credentials, "granted_scopes", None)
        or getattr(credentials, "scopes", None)
    )


def _authorize(credentials_path):
    if not credentials_path.exists():
        raise GoogleCredentialsNotFoundError(
            f"Google OAuth client credentials were not found at {credentials_path}."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    credentials = flow.run_local_server(port=0)
    missing_scopes = _missing_scopes(_authorized_scopes(credentials))
    if missing_scopes:
        missing = ", ".join(sorted(missing_scopes))
        raise GoogleInsufficientScopesError(
            "Google authorization did not grant all required permissions. "
            f"Missing: {missing}. Reauthorize and approve the requested access."
        )
    return credentials


def get_google_credentials():
    """Return credentials authorized for both Calendar and Gmail.

    A saved Calendar-only token is deliberately reauthorized rather than
    refreshed, because refreshing cannot grant Gmail access.
    """
    credentials_path, token_path = credential_paths()
    credentials = None

    if token_path.exists():
        token_scopes = _token_scopes(token_path)
        missing_scopes = _missing_scopes(token_scopes)
        if not missing_scopes:
            try:
                credentials = Credentials.from_authorized_user_file(str(token_path))
            except (OSError, ValueError) as error:
                raise GoogleTokenError(
                    f"Google token at {token_path} could not be loaded. "
                    "Delete it and authorize again."
                ) from error

            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except RefreshError:
                    credentials = None
            elif not credentials.valid:
                credentials = None

            if credentials is not None and credentials.valid:
                token_path.write_text(credentials.to_json(), encoding="utf-8")
                return credentials

    credentials = _authorize(credentials_path)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
