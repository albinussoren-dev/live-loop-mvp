from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
import sqlite3, secrets, subprocess, sys, os, time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .settings import settings
from .youtube import YouTubeService
DB=settings.database_url.replace("sqlite:///","") if settings.database_url.startswith("sqlite:///") else "looplive.db"
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 c=db(); c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT,channel_id TEXT,channel_title TEXT,access_token TEXT,refresh_token TEXT,created_at TEXT); CREATE TABLE IF NOT EXISTS streams(id TEXT PRIMARY KEY,user_id TEXT,title TEXT,video_id TEXT,source_url TEXT,loop INTEGER,quality TEXT,status TEXT,broadcast_id TEXT,stream_id TEXT,ingest_url TEXT,stream_key TEXT,created_at TEXT,started_at TEXT,stopped_at TEXT); CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,stream_id TEXT,level TEXT,message TEXT,created_at TEXT);'''); c.commit(); c.close()
def log(sid,level,message):
 c=db(); c.execute("INSERT INTO logs(stream_id,level,message,created_at) VALUES(?,?,?,?)",(sid,level,message,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()
class StreamCreate(BaseModel): title:str=Field(min_length=1,max_length=120); video_id:str=Field(min_length=3,max_length=32); source_url:Optional[str]=None; loop:bool=True; quality:str="1080p"
class StreamOut(BaseModel): id:str; title:str; video_id:str; source_url:Optional[str]; loop:bool; quality:str; status:str; youtube_broadcast_id:Optional[str]=None; youtube_stream_id:Optional[str]=None; started_at:Optional[str]=None
@asynccontextmanager
async def lifespan(app:FastAPI): init_db(); yield
app=FastAPI(title="LoopLive API",version="2.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
def token_or_401():
 c=db(); r=c.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 1").fetchone(); c.close()
 if not r: raise HTTPException(401,"Connect Google/YouTube first")
 return dict(r)
def row_stream(r): return StreamOut(id=r["id"],title=r["title"],video_id=r["video_id"],source_url=r["source_url"],loop=bool(r["loop"]),quality=r["quality"],status=r["status"],youtube_broadcast_id=r["broadcast_id"],youtube_stream_id=r["stream_id"],started_at=r["started_at"])
@app.get("/health")
def health(): return {"status":"ok","service":"looplive-api","version":app.version}
@app.get("/api/youtube/auth-url")
def auth_url(state:str="looplive"):
 if not settings.youtube_configured: raise HTTPException(503,"Configure Google OAuth credentials")
 return {"url":YouTubeService().authorization_url(state)}
@app.get("/api/youtube/callback")
def callback(code:Optional[str]=None,state:Optional[str]=None):
 if not code: raise HTTPException(400,"Missing OAuth code")
 cred=YouTubeService().exchange_code(code); ch=YouTubeService().channel(cred.token,cred.refresh_token)
 if not ch: raise HTTPException(400,"No YouTube channel found")
 c=db(); c.execute("DELETE FROM users"); uid=uuid4().hex; c.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)",(uid,None,ch["id"],ch["snippet"]["title"],cred.token,cred.refresh_token,datetime.now(timezone.utc).isoformat())); c.commit(); c.close(); return {"connected":True,"channel":{"id":ch["id"],"title":ch["snippet"]["title"]},"state":state}
@app.get("/api/youtube/channel")
def channel():
 u=token_or_401(); return {"id":u["channel_id"],"title":u["channel_title"]}
@app.get("/api/youtube/videos")
def videos():
 u=token_or_401(); return {"items":YouTubeService().videos(u["access_token"],u["refresh_token"])}
@app.post("/api/streams",response_model=StreamOut,status_code=201)
def create_stream(p:StreamCreate):
 u=token_or_401(); c=db(); n=c.execute("SELECT COUNT(*) n FROM streams WHERE status IN ('starting','live')").fetchone()["n"]
 if n>=settings.max_streams_per_pilot: c.close(); raise HTTPException(409,"Pilot stream limit reached")
 sid="stream_"+secrets.token_hex(5); c.execute("INSERT INTO streams(id,user_id,title,video_id,source_url,loop,quality,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(sid,u["id"],p.title,p.video_id,p.source_url,int(p.loop),p.quality,"ready",datetime.now(timezone.utc).isoformat())); c.commit(); r=c.execute("SELECT * FROM streams WHERE id=?",(sid,)).fetchone(); c.close(); return row_stream(r)
@app.get("/api/streams",response_model=list[StreamOut])
def streams():
 c=db(); r=c.execute("SELECT * FROM streams ORDER BY created_at DESC").fetchall(); c.close(); return [row_stream(x) for x in r]
@app.post("/api/streams/{sid}/start",response_model=StreamOut)
def start(sid:str):
 u=token_or_401(); c=db(); r=c.execute("SELECT * FROM streams WHERE id=?",(sid,)).fetchone(); c.close()
 if not r: raise HTTPException(404,"Stream not found")
 if not r["source_url"]: raise HTTPException(400,"A permitted media source URL is required. A YouTube video ID alone is metadata, not a downloadable media URL.")
 svc=YouTubeService(); b=svc.create_broadcast(u["access_token"],r["title"]); s=svc.create_stream(u["access_token"],r["title"],r["quality"]); svc.bind(u["access_token"],b["id"],s["id"]); ing=s["cdn"]["ingestionInfo"]
 c=db(); c.execute("UPDATE streams SET status='starting',broadcast_id=?,stream_id=?,ingest_url=?,stream_key=? WHERE id=?",(b["id"],s["id"],ing["ingestionAddress"],ing["streamName"],sid)); c.commit(); c.close(); log(sid,"info","YouTube broadcast, RTMP stream and binding created")
 subprocess.Popen([sys.executable,"-m","app.worker","--stream-id",sid,"--source",r["source_url"],"--ingest",ing["ingestionAddress"],"--key",ing["streamName"]]+([] if r["loop"] else ["--no-loop"]),cwd=os.path.dirname(__file__))
 time.sleep(4)
 try: svc.transition(u["access_token"],b["id"],"live"); status="live"; log(sid,"info","Broadcast transitioned to LIVE")
 except Exception as e: status="starting"; log(sid,"warn",f"Live transition pending: {e}")
 c=db(); now=datetime.now(timezone.utc).isoformat(); c.execute("UPDATE streams SET status=?,started_at=? WHERE id=?",(status,now,sid)); c.commit(); rr=c.execute("SELECT * FROM streams WHERE id=?",(sid,)).fetchone(); c.close(); return row_stream(rr)
@app.post("/api/streams/{sid}/stop",response_model=StreamOut)
def stop(sid:str):
 u=token_or_401(); c=db(); r=c.execute("SELECT * FROM streams WHERE id=?",(sid,)).fetchone(); c.close()
 if not r: raise HTTPException(404,"Stream not found")
 if r["broadcast_id"]:
  try: YouTubeService().transition(u["access_token"],r["broadcast_id"],"complete")
  except Exception as e: log(sid,"warn",f"YouTube transition failed: {e}")
 c=db(); now=datetime.now(timezone.utc).isoformat(); c.execute("UPDATE streams SET status='stopped',stopped_at=? WHERE id=?",(now,sid)); c.commit(); rr=c.execute("SELECT * FROM streams WHERE id=?",(sid,)).fetchone(); c.close(); log(sid,"info","Stream stopped"); return row_stream(rr)
@app.get("/api/streams/{sid}/logs")
def logs(sid:str):
 c=db(); r=c.execute("SELECT level,message,created_at FROM logs WHERE stream_id=? ORDER BY id DESC LIMIT 200",(sid,)).fetchall(); c.close(); return [dict(x) for x in r]
@app.get("/api/analytics")
def analytics():
 c=db(); total=c.execute("SELECT COUNT(*) n FROM streams").fetchone()["n"]; live=c.execute("SELECT COUNT(*) n FROM streams WHERE status IN ('starting','live')").fetchone()["n"]; events=c.execute("SELECT COUNT(*) n FROM logs").fetchone()["n"]; c.close(); return {"streams_total":total,"active_streams":live,"log_events":events}
