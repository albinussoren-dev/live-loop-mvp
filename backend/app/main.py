from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4
import hmac, os, secrets, sqlite3, subprocess, sys, threading, time

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .settings import settings
from .youtube import YouTubeService

DB = settings.database_url.replace("sqlite:///", "") if settings.database_url.startswith("sqlite:///") else "looplive.db"
serializer = URLSafeTimedSerializer(settings.session_secret or "dev-only-change-me")
fernet = Fernet(settings.encryption_key) if settings.encryption_key else None
workers: dict[str, subprocess.Popen] = {}
workers_lock = threading.Lock()


def db():
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY, google_sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL,
      name TEXT, picture TEXT, channel_id TEXT, channel_title TEXT,
      access_token TEXT, refresh_token TEXT NOT NULL, token_expiry TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS playlists (
      id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name TEXT NOT NULL, description TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS playlist_items (
      id TEXT PRIMARY KEY, playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
      youtube_video_id TEXT NOT NULL, title TEXT NOT NULL, source_uri TEXT NOT NULL,
      position INTEGER NOT NULL, created_at TEXT NOT NULL,
      UNIQUE(playlist_id, youtube_video_id)
    );
    CREATE TABLE IF NOT EXISTS streams (
      id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      playlist_id TEXT REFERENCES playlists(id), title TEXT NOT NULL, loop INTEGER NOT NULL DEFAULT 1,
      quality TEXT NOT NULL DEFAULT '1080p', status TEXT NOT NULL DEFAULT 'ready',
      broadcast_id TEXT, stream_id TEXT, ingest_url TEXT, stream_key TEXT,
      worker_pid INTEGER, restart_count INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, started_at TEXT, stopped_at TEXT
    );
    CREATE TABLE IF NOT EXISTS logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, stream_id TEXT NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
      level TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS schedules (
      id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE, title TEXT NOT NULL,
      start_at TEXT NOT NULL, interval_minutes INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
      last_run_at TEXT, next_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_stream_user_status ON streams(user_id,status);
    CREATE INDEX IF NOT EXISTS idx_logs_stream ON logs(stream_id,id DESC);
    CREATE INDEX IF NOT EXISTS idx_schedule_due ON schedules(enabled,next_run_at);
    """)
    c.commit(); c.close()


def enc(value: str) -> str:
    if not fernet: raise RuntimeError("ENCRYPTION_KEY is not configured")
    return fernet.encrypt(value.encode()).decode()


def dec(value: str) -> str:
    try:
        if not fernet: raise RuntimeError("ENCRYPTION_KEY is not configured")
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken as e: raise RuntimeError("Stored credential could not be decrypted") from e


def log(sid, level, message):
    c=db(); c.execute("INSERT INTO logs(stream_id,level,message,created_at) VALUES(?,?,?,?)",(sid,level,message,iso(now()))); c.commit(); c.close()


def session_user(request: Request):
    raw = request.cookies.get("looplive_session")
    if not raw: raise HTTPException(401,"Login required")
    try: data = serializer.loads(raw, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired): raise HTTPException(401,"Session expired")
    c=db(); u=c.execute("SELECT * FROM users WHERE id=?",(data.get("uid"),)).fetchone(); c.close()
    if not u: raise HTTPException(401,"User not found")
    return dict(u)


def require_csrf(request: Request):
    if request.method in {"GET","HEAD","OPTIONS"}: return
    cookie=request.cookies.get("looplive_csrf"); header=request.headers.get("x-csrf-token")
    # The custom header forces a CORS preflight. CORS is restricted to configured origins.
    if cookie and header is not None: return
    raise HTTPException(403,"CSRF validation failed")


def token_pair(user):
    return (dec(user["access_token"]) if user.get("access_token") else None), dec(user["refresh_token"])

class PlaylistCreate(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    description: str = Field(default="",max_length=500)
class PlaylistItemCreate(BaseModel):
    youtube_video_id: str = Field(min_length=3,max_length=32)
    title: str = Field(min_length=1,max_length=300)
    source_uri: str = Field(min_length=8,max_length=2000)
    position: int = Field(default=0,ge=0)
class StreamCreate(BaseModel):
    title: str = Field(min_length=1,max_length=120)
    playlist_id: Optional[str] = None
    source_url: Optional[str] = None
    loop: bool = True
    quality: str = "1080p"
class ScheduleCreate(BaseModel):
    playlist_id: str
    title: str = Field(min_length=1,max_length=120)
    start_at: str
    interval_minutes: Optional[int] = Field(default=None,ge=15)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.production_secrets_configured:
        raise RuntimeError("SESSION_SECRET (32+ chars) and ENCRYPTION_KEY are required")
    init_db()
    t=threading.Thread(target=scheduler_loop,daemon=True); t.start()
    yield
    with workers_lock:
        for p in workers.values():
            if p.poll() is None: p.terminate()

app=FastAPI(title="LoopLive API",version="3.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok","service":"looplive-api","version":app.version}

@app.get("/api/auth/status")
def auth_status(request: Request):
    try:
        u=session_user(request); return {"authenticated":True,"user":{"email":u["email"],"name":u["name"],"picture":u["picture"]}}
    except HTTPException: return {"authenticated":False}

@app.get("/api/youtube/auth-url")
def auth_url():
    if not settings.youtube_configured: raise HTTPException(503,"Configure Google OAuth credentials")
    state=serializer.dumps({"nonce":secrets.token_urlsafe(24),"iat":int(time.time())},salt="youtube-oauth")
    return {"url":YouTubeService().authorization_url(state)}

@app.get("/api/youtube/callback")
def callback(code:Optional[str]=None,state:Optional[str]=None):
    if not code or not state: raise HTTPException(400,"Missing OAuth parameters")
    try: serializer.loads(state,max_age=600,salt="youtube-oauth")
    except (BadSignature,SignatureExpired): raise HTTPException(400,"Invalid or expired OAuth state")
    svc=YouTubeService(); cred=svc.exchange_code(code); info=svc.userinfo(cred.token); ch=svc.channel(cred.token,cred.refresh_token)
    if not ch: raise HTTPException(400,"No YouTube channel found")
    uid=uuid4().hex; created=iso(now()); expiry=iso(cred.expiry) if cred.expiry else None
    c=db(); existing=c.execute("SELECT id FROM users WHERE google_sub=?",(info["sub"],)).fetchone()
    if existing: uid=existing["id"]
    c.execute("""INSERT INTO users(id,google_sub,email,name,picture,channel_id,channel_title,access_token,refresh_token,token_expiry,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email,name=excluded.name,picture=excluded.picture,channel_id=excluded.channel_id,channel_title=excluded.channel_title,access_token=excluded.access_token,refresh_token=excluded.refresh_token,token_expiry=excluded.token_expiry,updated_at=excluded.updated_at""",
      (uid,info["sub"],info.get("email",""),info.get("name"),info.get("picture"),ch["id"],ch["snippet"]["title"],enc(cred.token),enc(cred.refresh_token),expiry,created,created)); c.commit(); c.close()
    session=serializer.dumps({"uid":uid},salt="session"); csrf=secrets.token_urlsafe(32)
    from starlette.responses import RedirectResponse
    r=RedirectResponse(settings.frontend_url+"/?connected=1",status_code=302)
    secure=settings.frontend_url.startswith("https://")
    r.set_cookie("looplive_session",session,max_age=settings.session_max_age,httponly=True,samesite="none" if secure else "lax",secure=secure,path="/")
    r.set_cookie("looplive_csrf",csrf,max_age=settings.session_max_age,httponly=False,samesite="none" if secure else "lax",secure=secure,path="/")
    return r

@app.post("/api/auth/logout")
def logout(request:Request,response:Response):
    require_csrf(request); response.delete_cookie("looplive_session",path="/"); response.delete_cookie("looplive_csrf",path="/"); return {"ok":True}

@app.get("/api/youtube/channel")
def channel(request:Request):
    u=session_user(request); return {"id":u["channel_id"],"title":u["channel_title"]}

@app.get("/api/youtube/videos")
def videos(request:Request):
    u=session_user(request); access,refresh=token_pair(u); return {"items":YouTubeService().videos(access,refresh)}

@app.get("/api/playlists")
def playlists(request:Request):
    u=session_user(request); c=db(); rows=c.execute("SELECT * FROM playlists WHERE user_id=? ORDER BY updated_at DESC",(u["id"],)).fetchall(); out=[]
    for p in rows:
        items=c.execute("SELECT * FROM playlist_items WHERE playlist_id=? ORDER BY position,id",(p["id"],)).fetchall(); out.append({**dict(p),"items":[dict(x) for x in items]})
    c.close(); return out

@app.post("/api/playlists",status_code=201)
def create_playlist(p:PlaylistCreate,request:Request):
    require_csrf(request); u=session_user(request); pid="pl_"+secrets.token_hex(6); t=iso(now()); c=db(); c.execute("INSERT INTO playlists VALUES(?,?,?,?,?,?)",(pid,u["id"],p.name,p.description,t,t)); c.commit(); c.close(); return {"id":pid,"name":p.name,"description":p.description,"items":[]}

@app.post("/api/playlists/{pid}/items",status_code=201)
def add_playlist_item(pid:str,p:PlaylistItemCreate,request:Request):
    require_csrf(request); u=session_user(request); c=db(); owner=c.execute("SELECT id FROM playlists WHERE id=? AND user_id=?",(pid,u["id"])).fetchone()
    if not owner: c.close(); raise HTTPException(404,"Playlist not found")
    iid="pli_"+secrets.token_hex(6); c.execute("INSERT OR REPLACE INTO playlist_items(id,playlist_id,youtube_video_id,title,source_uri,position,created_at) VALUES(?,?,?,?,?,?,?)",(iid,pid,p.youtube_video_id,p.title,p.source_uri,p.position,iso(now()))); c.execute("UPDATE playlists SET updated_at=? WHERE id=?",(iso(now()),pid)); c.commit(); c.close(); return {"id":iid,"playlist_id":pid,**p.model_dump()}

@app.delete("/api/playlists/{pid}")
def delete_playlist(pid:str,request:Request):
    require_csrf(request); u=session_user(request); c=db(); c.execute("DELETE FROM playlists WHERE id=? AND user_id=?",(pid,u["id"])); c.commit(); c.close(); return {"ok":True}

@app.get("/api/streams")
def streams(request:Request):
    u=session_user(request); c=db(); rows=c.execute("SELECT * FROM streams WHERE user_id=? ORDER BY created_at DESC",(u["id"],)).fetchall(); c.close(); return [dict(x) for x in rows]

@app.post("/api/streams",status_code=201)
def create_stream(p:StreamCreate,request:Request):
    require_csrf(request); u=session_user(request); c=db(); n=c.execute("SELECT COUNT(*) n FROM streams WHERE user_id=? AND status IN ('starting','live')",(u["id"],)).fetchone()["n"]
    if n>=settings.max_streams_per_pilot: c.close(); raise HTTPException(409,"Active stream limit reached")
    if not p.playlist_id and not p.source_url: c.close(); raise HTTPException(400,"playlist_id or source_url is required")
    sid="stream_"+secrets.token_hex(6); t=iso(now()); c.execute("INSERT INTO streams(id,user_id,playlist_id,title,loop,quality,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(sid,u["id"],p.playlist_id,p.title,int(p.loop),p.quality,"ready",t)); c.commit(); c.close(); return {"id":sid,"title":p.title,"status":"ready"}

def sources_for_stream(c,s):
    if s["playlist_id"]:
        rows=c.execute("SELECT source_uri FROM playlist_items WHERE playlist_id=? ORDER BY position,id",(s["playlist_id"],)).fetchall(); return [x["source_uri"] for x in rows]
    return []

def do_start(sid,user_id):
    c=db(); s=c.execute("SELECT * FROM streams WHERE id=? AND user_id=?",(sid,user_id)).fetchone(); u=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone(); c.close()
    if not s or not u: raise HTTPException(404,"Stream not found")
    c=db(); sources=sources_for_stream(c,s); c.close()
    if not sources: raise HTTPException(400,"Playlist has no permitted media sources")
    access,refresh=token_pair(u); svc=YouTubeService(); b=svc.create_broadcast(access,s["title"]); st=svc.create_stream(access,s["title"],s["quality"]); svc.bind(access,b["id"],st["id"]); ing=st["cdn"]["ingestionInfo"]
    cmd=[sys.executable,"-m","app.worker","--stream-id",sid,"--source",",".join(sources),"--ingest",ing["ingestionAddress"],"--key",ing["streamName"]]
    if not s["loop"]: cmd.append("--no-loop")
    p=subprocess.Popen(cmd,cwd=os.path.dirname(__file__))
    with workers_lock: workers[sid]=p
    c=db(); c.execute("UPDATE streams SET status='starting',broadcast_id=?,stream_id=?,ingest_url=?,stream_key=?,worker_pid=? WHERE id=?",(b["id"],st["id"],ing["ingestionAddress"],ing["streamName"],p.pid,sid)); c.commit(); c.close(); log(sid,"info","Broadcast and RTMPS worker created")
    time.sleep(4)
    try: svc.transition(access,b["id"],"live"); status="live"; log(sid,"info","YouTube broadcast is LIVE")
    except Exception as e: status="starting"; log(sid,"warn",f"Live transition pending: {e}")
    c=db(); c.execute("UPDATE streams SET status=?,started_at=? WHERE id=?",(status,iso(now()),sid)); c.commit(); c.close()

@app.post("/api/streams/{sid}/start")
def start_stream(sid:str,request:Request):
    require_csrf(request); u=session_user(request); do_start(sid,u["id"]); c=db(); r=c.execute("SELECT * FROM streams WHERE id=?",(sid,)).fetchone(); c.close(); return dict(r)

@app.post("/api/streams/{sid}/stop")
def stop_stream(sid:str,request:Request):
    require_csrf(request); u=session_user(request); c=db(); s=c.execute("SELECT * FROM streams WHERE id=? AND user_id=?",(sid,u["id"])).fetchone(); c.close()
    if not s: raise HTTPException(404,"Stream not found")
    with workers_lock:
        p=workers.get(sid)
        if p and p.poll() is None: p.terminate()
        workers.pop(sid,None)
    if s["broadcast_id"]:
        try:
            access,refresh=token_pair(u); YouTubeService().transition(access,s["broadcast_id"],"complete")
        except Exception as e: log(sid,"warn",f"YouTube stop failed: {e}")
    c=db(); c.execute("UPDATE streams SET status='stopped',stopped_at=? WHERE id=?",(iso(now()),sid)); c.commit(); c.close(); log(sid,"info","Stream stopped")
    return {"id":sid,"status":"stopped"}

@app.get("/api/streams/{sid}/status")
def stream_status(sid:str,request:Request):
    u=session_user(request); c=db(); s=c.execute("SELECT * FROM streams WHERE id=? AND user_id=?",(sid,u["id"])).fetchone(); c.close()
    if not s: raise HTTPException(404,"Stream not found")
    yt=None
    if s["broadcast_id"]:
        try: access,refresh=token_pair(u); yt=YouTubeService().broadcast(access,s["broadcast_id"])
        except Exception as e: yt={"error":str(e)}
    return {"stream":dict(s),"youtube":yt,"worker_alive":sid in workers and workers[sid].poll() is None}

@app.get("/api/streams/{sid}/logs")
def logs(sid:str,request:Request):
    u=session_user(request); c=db(); owner=c.execute("SELECT id FROM streams WHERE id=? AND user_id=?",(sid,u["id"])).fetchone(); rows=c.execute("SELECT level,message,created_at FROM logs WHERE stream_id=? ORDER BY id DESC LIMIT 500",(sid,)).fetchall() if owner else []; c.close()
    if not owner: raise HTTPException(404,"Stream not found")
    return [dict(x) for x in rows]

@app.get("/api/analytics")
def analytics(request:Request):
    u=session_user(request); c=db(); total=c.execute("SELECT COUNT(*) n FROM streams WHERE user_id=?",(u["id"],)).fetchone()["n"]; live=c.execute("SELECT COUNT(*) n FROM streams WHERE user_id=? AND status IN ('starting','live')",(u["id"],)).fetchone()["n"]; logs_count=c.execute("SELECT COUNT(*) n FROM logs WHERE stream_id IN (SELECT id FROM streams WHERE user_id=?)",(u["id"],)).fetchone()["n"]; playlists=c.execute("SELECT COUNT(*) n FROM playlists WHERE user_id=?",(u["id"],)).fetchone()["n"]; schedules=c.execute("SELECT COUNT(*) n FROM schedules WHERE user_id=? AND enabled=1",(u["id"],)).fetchone()["n"]; c.close(); return {"streams_total":total,"active_streams":live,"log_events":logs_count,"playlists":playlists,"active_schedules":schedules}

@app.get("/api/schedules")
def schedules(request:Request):
    u=session_user(request); c=db(); rows=c.execute("SELECT * FROM schedules WHERE user_id=? ORDER BY next_run_at",(u["id"],)).fetchall(); c.close(); return [dict(x) for x in rows]

@app.post("/api/schedules",status_code=201)
def create_schedule(p:ScheduleCreate,request:Request):
    require_csrf(request); u=session_user(request)
    try: start=datetime.fromisoformat(p.start_at.replace("Z","+00:00"))
    except ValueError: raise HTTPException(400,"start_at must be ISO-8601")
    c=db(); owner=c.execute("SELECT id FROM playlists WHERE id=? AND user_id=?",(p.playlist_id,u["id"])).fetchone()
    if not owner: c.close(); raise HTTPException(404,"Playlist not found")
    sid="sch_"+secrets.token_hex(6); t=iso(now()); c.execute("INSERT INTO schedules VALUES(?,?,?,?,?,?,?,?,?,?)",(sid,u["id"],p.playlist_id,p.title,iso(start),p.interval_minutes,1,None,iso(start),t,t)); c.commit(); c.close(); return {"id":sid,"next_run_at":iso(start),"enabled":True}

@app.post("/api/schedules/{sid}/toggle")
def toggle_schedule(sid:str,request:Request):
    require_csrf(request); u=session_user(request); c=db(); r=c.execute("SELECT enabled FROM schedules WHERE id=? AND user_id=?",(sid,u["id"])).fetchone()
    if not r: c.close(); raise HTTPException(404,"Schedule not found")
    enabled=0 if r["enabled"] else 1; c.execute("UPDATE schedules SET enabled=?,updated_at=? WHERE id=?",(enabled,iso(now()),sid)); c.commit(); c.close(); return {"enabled":bool(enabled)}


def scheduler_loop():
    while True:
        try:
            c=db(); due=c.execute("SELECT * FROM schedules WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at LIMIT 10",(iso(now()),)).fetchall()
            for s in due:
                next_time=now()+timedelta(minutes=s["interval_minutes"] or 1440)
                c.execute("UPDATE schedules SET last_run_at=?,next_run_at=?,updated_at=? WHERE id=? AND enabled=1",(iso(now()),iso(next_time),iso(now()),s["id"])); c.commit()
                try:
                    uid=s["user_id"]; c2=db(); n=c2.execute("SELECT COUNT(*) n FROM streams WHERE user_id=? AND status IN ('starting','live')",(uid,)).fetchone()["n"]
                    if n<settings.max_streams_per_pilot:
                        sid="stream_"+secrets.token_hex(6); t=iso(now()); c2.execute("INSERT INTO streams(id,user_id,playlist_id,title,loop,quality,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(sid,uid,s["playlist_id"],s["title"],1,"1080p","ready",t)); c2.commit(); c2.close(); do_start(sid,uid)
                    else: c2.close()
                except Exception as e: print("schedule run failed",e)
            c.close()
        except Exception as e: print("scheduler error",e)
        time.sleep(max(5,settings.scheduler_interval))
