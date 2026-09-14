from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="LoopLive API", version="0.1.0")

class StreamCreate(BaseModel):
    title: str
    video_id: str
    loop: bool = True
    quality: str = "1080p"

class Stream(StreamCreate):
    id: str
    status: str = "ready"

streams: dict[str, Stream] = {}

@app.get("/health")
def health():
    return {"status": "ok", "service": "looplive-api"}

@app.get("/api/streams")
def list_streams():
    return list(streams.values())

@app.post("/api/streams", response_model=Stream)
def create_stream(payload: StreamCreate):
    stream_id = f"stream_{len(streams)+1}"
    stream = Stream(id=stream_id, **payload.model_dump())
    streams[stream_id] = stream
    return stream

@app.post("/api/streams/{stream_id}/start", response_model=Stream)
def start_stream(stream_id: str):
    stream = streams[stream_id]
    stream.status = "starting"
    return stream

@app.post("/api/streams/{stream_id}/stop", response_model=Stream)
def stop_stream(stream_id: str):
    stream = streams[stream_id]
    stream.status = "stopped"
    return stream

@app.get("/api/youtube/callback")
def youtube_callback(code: Optional[str] = None):
    return {"configured": bool(code), "message": "OAuth callback placeholder; add Google OAuth credentials in production."}

@app.get("/api/youtube/videos")
def youtube_videos():
    return {"items": [], "message": "Connect an authorized YouTube channel to load videos."}
