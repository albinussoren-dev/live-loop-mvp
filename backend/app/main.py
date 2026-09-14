from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .settings import settings
from .youtube import YouTubeService

streams: dict[str, dict] = {}


class StreamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    video_id: str = Field(min_length=3, max_length=32)
    loop: bool = True
    quality: str = "1080p"
    youtube_channel_id: Optional[str] = None


class StreamOut(StreamCreate):
    id: str
    status: str
    youtube_broadcast_id: Optional[str] = None
    youtube_stream_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="LoopLive API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_stream_or_404(stream_id: str) -> dict:
    stream = streams.get(stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    return stream


@app.get("/health")
def health():
    return {"status": "ok", "service": "looplive-api", "version": app.version}


@app.get("/api/streams", response_model=list[StreamOut])
def list_streams():
    return list(streams.values())


@app.post("/api/streams", response_model=StreamOut, status_code=201)
def create_stream(payload: StreamCreate):
    if len(streams) >= settings.max_streams_per_pilot:
        raise HTTPException(status_code=409, detail="Pilot stream limit reached")
    stream_id = f"stream_{uuid4().hex[:10]}"
    stream = {"id": stream_id, "status": "ready", "youtube_broadcast_id": None, "youtube_stream_id": None, **payload.model_dump()}
    streams[stream_id] = stream
    return stream


@app.post("/api/streams/{stream_id}/start", response_model=StreamOut)
def start_stream(stream_id: str):
    stream = get_stream_or_404(stream_id)
    if stream["status"] == "live":
        return stream
    stream["status"] = "starting"
    # A worker should consume this job and publish the authorized media source to YouTube RTMP.
    stream["status"] = "ready_to_publish"
    return stream


@app.post("/api/streams/{stream_id}/stop", response_model=StreamOut)
def stop_stream(stream_id: str):
    stream = get_stream_or_404(stream_id)
    stream["status"] = "stopped"
    return stream


@app.get("/api/youtube/config")
def youtube_config():
    return {"configured": settings.youtube_configured, "redirect_uri": settings.youtube_redirect_uri}


@app.get("/api/youtube/auth-url")
def youtube_auth_url(state: str = Query(default="looplive")):
    service = YouTubeService()
    if not settings.youtube_configured:
        raise HTTPException(status_code=503, detail="Configure Google OAuth credentials first")
    return {"url": service.authorization_url(state)}


@app.get("/api/youtube/callback")
def youtube_callback(code: Optional[str] = None, state: Optional[str] = None):
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth authorization code")
    if not settings.youtube_configured:
        raise HTTPException(status_code=503, detail="Configure Google OAuth credentials first")
    service = YouTubeService()
    tokens = service.exchange_code(code)
    # Store tokens encrypted in a real database/secret store. Never expose refresh tokens to the browser.
    return {"connected": True, "state": state, "token_type": tokens.get("token_type", "Bearer")}


@app.get("/api/youtube/videos")
def youtube_videos(channel_id: Optional[str] = None):
    if not settings.youtube_configured:
        return {"items": [], "configured": False, "message": "Configure Google OAuth credentials to load authorized videos."}
    return {"items": [], "configured": True, "channel_id": channel_id, "message": "Connect a user token and query the YouTube Data API for that authorized channel."}


@app.get("/api/youtube/live/health")
def youtube_live_health():
    return {"configured": settings.youtube_configured, "live_api": settings.youtube_configured, "message": "YouTube Live API is ready for credentialed integration."}
