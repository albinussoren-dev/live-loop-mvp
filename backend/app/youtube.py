from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from .settings import settings
SCOPES=["https://www.googleapis.com/auth/youtube","https://www.googleapis.com/auth/youtube.force-ssl"]
class YouTubeService:
 def _flow(self):
  cfg={"web":{"client_id":settings.google_client_id,"client_secret":settings.google_client_secret,"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[settings.youtube_redirect_uri]}}
  f=Flow.from_client_config(cfg,scopes=SCOPES); f.redirect_uri=settings.youtube_redirect_uri; return f
 def authorization_url(self,state): return self._flow().authorization_url(access_type="offline",include_granted_scopes="true",prompt="consent",state=state)[0]
 def exchange_code(self,code): f=self._flow(); f.fetch_token(code=code); return f.credentials
 def credentials(self,token,refresh_token=None,expiry=None):
  c=Credentials(token=token,refresh_token=refresh_token,token_uri="https://oauth2.googleapis.com/token",client_id=settings.google_client_id,client_secret=settings.google_client_secret,scopes=SCOPES,expiry=expiry)
  if c.expired and c.refresh_token: c.refresh(Request())
  return c
 def api(self,token,refresh_token=None): return build("youtube","v3",credentials=self.credentials(token,refresh_token),cache_discovery=False)
 def channel(self,token,refresh_token=None):
  r=self.api(token,refresh_token).channels().list(part="snippet,contentDetails,statistics",mine=True).execute(); return (r.get("items") or [None])[0]
 def videos(self,token,refresh_token=None,limit=50):
  yt=self.api(token,refresh_token); ch=self.channel(token,refresh_token)
  if not ch:return []
  pid=ch["contentDetails"]["relatedPlaylists"]["uploads"]; out=[]; page=None
  while len(out)<limit:
   r=yt.playlistItems().list(part="snippet,contentDetails",playlistId=pid,maxResults=min(50,limit-len(out)),pageToken=page).execute(); ids=[x["contentDetails"]["videoId"] for x in r.get("items",[])]
   if ids: out.extend(yt.videos().list(part="snippet,contentDetails,status",id=",".join(ids)).execute().get("items",[]))
   page=r.get("nextPageToken")
   if not page:break
  return out[:limit]
 def create_broadcast(self,token,title,privacy="unlisted",description=""):
  start=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat().replace("+00:00","Z")
  return self.api(token).liveBroadcasts().insert(part="snippet,status,contentDetails",body={"snippet":{"title":title,"description":description,"scheduledStartTime":start},"status":{"privacyStatus":privacy},"contentDetails":{"enableAutoStart":False,"enableAutoStop":False}}).execute()
 def create_stream(self,token,title,resolution="1080p",fps="30fps"):
  return self.api(token).liveStreams().insert(part="snippet,cdn,contentDetails,status",body={"snippet":{"title":title},"cdn":{"ingestionType":"rtmp","resolution":resolution,"frameRate":fps}}).execute()
 def bind(self,token,broadcast_id,stream_id): return self.api(token).liveBroadcasts().bind(part="id,snippet,contentDetails,status",id=broadcast_id,streamId=stream_id).execute()
 def transition(self,token,broadcast_id,status): return self.api(token).liveBroadcasts().transition(part="id,snippet,status",broadcastStatus=status,id=broadcast_id).execute()
 def broadcast(self,token,broadcast_id):
  r=self.api(token).liveBroadcasts().list(part="id,snippet,status,contentDetails",id=broadcast_id).execute(); return (r.get("items") or [None])[0]
