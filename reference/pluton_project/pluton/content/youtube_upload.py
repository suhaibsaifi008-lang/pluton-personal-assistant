"""
Uploads finished videos to YouTube via the Data API v3.

Requires a one-time setup you do yourself in Google Cloud Console (free):
1. Create a project at https://console.cloud.google.com
2. Enable the "YouTube Data API v3"
3. Create OAuth credentials (Desktop app type), download the JSON
4. Save it to the path set in config.YOUTUBE_CLIENT_SECRETS

The first upload will open a browser window asking you to log into the
YouTube account you want Pluton posting to — after that, it's cached and
runs unattended.
"""

import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    def __init__(self):
        self.client_secrets = os.path.expandvars(config.YOUTUBE_CLIENT_SECRETS)
        self.token_path = os.path.expandvars(config.YOUTUBE_TOKEN_FILE)
        self.enabled = os.path.exists(self.client_secrets)
        self.service = None

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets, SCOPES)
                creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "wb") as f:
                pickle.dump(creds, f)

        self.service = build("youtube", "v3", credentials=creds)

    def upload(self, video_path, title, description, tags=None, privacy="unlisted"):
        if not self.enabled:
            raise RuntimeError(
                "No YouTube client secrets file found at "
                f"{self.client_secrets} — set up OAuth first (see README)."
            )
        if not self.service:
            self._authenticate()

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags or [],
                "categoryId": "24",  # Entertainment
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = self.service.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            _, response = request.next_chunk()

        return response.get("id")
