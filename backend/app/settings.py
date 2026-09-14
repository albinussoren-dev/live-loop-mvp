import os
from dataclasses import dataclass
@dataclass(frozen=True)
class Settings:
 cors_origins:list[str]; max_streams_per_pilot:int; google_client_id:str; google_client_secret:str; youtube_redirect_uri:str; database_url:str
 @property
 def youtube_configured(self): return bool(self.google_client_id and self.google_client_secret and self.youtube_redirect_uri)
settings=Settings(cors_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:3000").split(",") if x.strip()],max_streams_per_pilot=int(os.getenv("MAX_STREAMS_PER_PILOT","2")),google_client_id=os.getenv("GOOGLE_CLIENT_ID",""),google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET",""),youtube_redirect_uri=os.getenv("YOUTUBE_REDIRECT_URI","http://localhost:8000/api/youtube/callback"),database_url=os.getenv("DATABASE_URL","sqlite:///looplive.db"))
