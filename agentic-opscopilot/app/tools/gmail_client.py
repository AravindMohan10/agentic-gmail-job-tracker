from __future__ import annotations

import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build


# Read-only scope for safety
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

DEFAULT_CREDENTIALS_FILE = "credentials.json"
DEFAULT_TOKEN_FILE = "token.json"


def get_gmail_service(
    credentials_file: Optional[str] = None,
    token_file: Optional[str] = None,
) -> Resource:
    """
    Returns an authenticated Gmail API service.

    - Uses OAuth2 installed-app flow
    - Refreshes expired tokens automatically
    - Stores tokens locally

    Paths default to credentials.json and token.json in cwd, or use
    GMAIL_CREDENTIALS_FILE and GMAIL_TOKEN_FILE env vars.
    """
    credentials_file = credentials_file or os.environ.get(
        "GMAIL_CREDENTIALS_FILE", DEFAULT_CREDENTIALS_FILE
    )
    token_file = token_file or os.environ.get(
        "GMAIL_TOKEN_FILE", DEFAULT_TOKEN_FILE
    )

    if not os.path.exists(credentials_file):
        raise FileNotFoundError(
            f"Gmail credentials not found: {credentials_file}. "
            "Download OAuth client credentials from Google Cloud Console "
            "(APIs & Services → Credentials → Create OAuth 2.0 Client ID → Desktop app), "
            "save as credentials.json, or set GMAIL_CREDENTIALS_FILE to its path."
        )

    creds: Optional[Credentials] = None

    # Load existing token
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If no valid credentials, refresh or authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file,
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        # Save updated token
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)