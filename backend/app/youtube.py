from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from .settings import settings

SCOPES = ["https://www.googleapis.com/auth/youtube"]

class YouTubeService:
    def _flow(self) -> Flow:
        cfg={"web":{"client_id":settings.google_client_id,"client_secret":settings.google_client_secret,"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[settings.youtube_redirect_uri]}}
        flow=Flow.from_client_config(cfg, scopes=SCOPES)
        flow.redirect_uri=settings.youtube_redirect_uri
        return flow

    def authorization_url(self,state:str):
        url,_=self._flow().authorization_url(access_type="offline",include_granted_scopes="true",prompt="consent",state=state)
        return url

    def exchange_code(self,code:str):
        flow=self._flow(); flow.fetch_token(code=code); return flow.credentials

    def credentials(self, token:str, refresh_token:str|None=None, expiry=None):
        c=Credentials(token=token,refresh_token=refresh_token,token_uri="https://oauth2.googleapis.com/token",client_id=settings.google_client_id,client_secret=settings.google_client_secret,scopes=SCOPES,expiry=expiry)
        if c.expired and c.refresh_token: c.refresh(Request())
        return c

    def api(self, token:str, refresh_token:str|None=None):
        return build("youtube","v3",credentials=self.credentials(token,refresh_token),cache_discovery=False)

    def channel(self, token:str, refresh_token:str|None=None):
        r=self.api(token,refresh_token).channels().list(part="snippet,contentDetails,statistics",mine=True).execute()
        return (r.get("items") or [None])[0]

    def videos(self, token:str, refresh_token:str|None=None, limit:int=50):
        yt=self.api(token,refresh_token); ch=self.channel(token,refresh_token)
        if not ch: return []
        uploads=ch["contentDetails"]["relatedPlaylists"]["uploads"]
        items=[]; page=None
        while len(items)<limit:
            r=yt.playlistItems().list(part="snippet,contentDetails",playlistId=uploads,maxResults=min(50,limit-len(items)),pageToken=page).execute()
            ids=[x["contentDetails"]["videoId"] for x in r.get("items",[])]
            if ids: items.extend(yt.videos().list(part="snippet,contentDetails,status",id=",".join(ids)).execute().get("items",[]))
            page=r.get("nextPageToken")
            if not page: break
        return items[:limit]

    def create_broadcast(self, token, title, privacy="unlisted", description=""):
        yt=self.api(token)
        return yt.liveBroadcasts().insert(part="snippet,status,contentDetails",body={"snippet":{"title":title,"description":description,"scheduledStartTime":"2026-09-14T12:00:00Z"},"status":{"privacyStatus":privacy},"contentDetails":{"enableAutoStart":False,"enableAutoStop":False}}).execute()

    def create_stream(self, token, title, resolution="1080p", fps="30fps"):
        yt=self.api(token)
        return yt.liveStreams().insert(part="snippet,cdn,contentDetails,status",body={"snippet":{"title":title},"cdn":{"ingestionType":"rtmp","resolution":resolution,"frameRate":fps}}).execute()

    def bind(self, token, broadcast_id, stream_id):
        return self.api(token).liveBroadcasts().bind(part="id,snippet,contentDetails,status",id=broadcast_id,streamId=stream_id).execute()

    def transition(self, token, broadcast_id, status):
        return self.api(token).liveBroadcasts().transition(part="id,snippet,status",broadcastStatus=status,id=broadcast_id).execute()

    def broadcast(self, token, broadcast_id):
        r=self.api(token).liveBroadcasts().list(part="id,snippet,status,contentDetails",id=broadcast_id).execute(); return (r.get("items") or [None])[0]
