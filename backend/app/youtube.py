from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from .settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
]


class YouTubeService:
    def _flow(self) -> Flow:
        client_config = {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.youtube_redirect_uri],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = settings.youtube_redirect_uri
        return flow

    def authorization_url(self, state: str) -> str:
        flow = self._flow()
        url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
        return url

    def exchange_code(self, code: str) -> dict:
        flow = self._flow()
        flow.fetch_token(code=code)
        return flow.credentials_to_dict() if hasattr(flow, "credentials_to_dict") else {
            "token_type": "Bearer",
            "refresh_token": flow.credentials.refresh_token,
            "scopes": flow.credentials.scopes,
        }

    @staticmethod
    def videos_from_credentials(token: str, refresh_token: str | None = None, client_id: str | None = None, client_secret: str | None = None):
        credentials = Credentials(token=token, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token", client_id=client_id, client_secret=client_secret, scopes=SCOPES)
        youtube = build("youtube", "v3", credentials=credentials)
        return youtube.search().list(part="snippet", forMine=True, type="video", maxResults=50).execute()
