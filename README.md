# LoopLive — Production V1

LoopLive is a YouTube Live automation platform for streaming **authorized media sources** continuously. V1 adds secure Google sessions, persistent playlists, broadcast/RTMPS/FFmpeg orchestration, auto-restart, operational monitoring, logs, analytics and persistent scheduling.

> LoopLive does not scrape or download arbitrary YouTube watch URLs. A YouTube `videoId` is metadata, not a downloadable media URL. Each playlist item therefore requires a media source URL that the operator owns or is authorized to use.

## V1 flow

```text
Google Login
      ↓
Secure Session + CSRF
      ↓
YouTube Channel
      ↓
Uploaded Videos
      ↓
Persistent Playlists
      ↓
Create YouTube Broadcast + Live Stream
      ↓
RTMPS Ingest
      ↓
FFmpeg Worker
      ↓
Auto Restart
      ↓
Live Monitoring
      ↓
Operational Logs
      ↓
Analytics
      ↓
Persistent Scheduling
```

## V1 capabilities

- Google OAuth with signed state validation
- Signed HTTP-only application session
- CSRF protection for state-changing browser requests
- Per-Google-user YouTube credentials
- Encrypted access/refresh tokens at rest with Fernet
- YouTube channel and uploaded-video retrieval
- Persistent playlists and playlist items
- Multiple authorized media sources per playlist
- YouTube broadcast creation and stream binding
- RTMPS/FFmpeg worker execution
- Continuous looping and worker auto-restart
- Graceful worker termination from the dashboard
- Live YouTube broadcast status monitoring
- FFmpeg operational logs
- Basic per-user analytics
- Persistent schedules with daily/repeating execution
- Per-user active-stream pilot limit
- Docker runtime with FFmpeg

## Architecture

```text
                  ┌─────────────────────────┐
                  │   Next.js / Netlify     │
                  │   Production Dashboard  │
                  └────────────┬────────────┘
                               │ HTTPS + Cookie Session
                               ▼
                  ┌─────────────────────────┐
                  │       FastAPI API       │
                  │ Auth · YouTube · Jobs   │
                  └───────┬─────────┬───────┘
                          │         │
                          ▼         ▼
                  ┌───────────┐  ┌──────────────┐
                  │ SQLite V1 │  │ FFmpeg Worker │
                  │ WAL mode  │  │ RTMPS ingest  │
                  └───────────┘  └───────┬──────┘
                                         ▼
                                  ┌─────────────┐
                                  │ YouTube Live│
                                  └─────────────┘
```

V1 is designed for a small pilot on a persistent backend host. For horizontal scaling beyond a single worker node, replace SQLite with PostgreSQL and move worker execution/scheduling to Redis-backed jobs.

## Repository

```text
live-loop-mvp/
├── app/
│   ├── page.tsx
│   ├── globals.css
│   └── layout.tsx
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── security.py
│   │   ├── settings.py
│   │   ├── youtube.py
│   │   └── worker.py
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
├── package.json
└── README.md
```

## Environment

Copy `.env.example` to `.env` and configure:

```env
NEXT_PUBLIC_API_BASE_URL=https://YOUR-BACKEND-DOMAIN
FRONTEND_URL=https://YOUR-NETLIFY-DOMAIN
CORS_ORIGINS=https://YOUR-NETLIFY-DOMAIN
MAX_STREAMS_PER_PILOT=2
DATABASE_URL=sqlite:///looplive.db
SCHEDULER_INTERVAL=15
SESSION_MAX_AGE=604800
SESSION_SECRET=use-a-long-random-secret-at-least-32-characters
ENCRYPTION_KEY=YOUR_FERNET_KEY
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET
YOUTUBE_REDIRECT_URI=https://YOUR-BACKEND-DOMAIN/api/youtube/callback
```

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit real secrets. GitHub explicitly warns against committing passwords or API keys. citeturn0search1

## Google Cloud setup

Enable:

- YouTube Data API v3
- YouTube Live Streaming API

Create a Google OAuth Web Client and set the backend callback URL as an authorized redirect URI.

Local callback:

```text
http://localhost:8000/api/youtube/callback
```

Production callback:

```text
https://YOUR-BACKEND-DOMAIN/api/youtube/callback
```

## Local development

Frontend:

```bash
npm install
npm run dev
```

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Docker:

```bash
docker compose up --build
```

## V1 API

### Authentication

```text
GET  /api/auth/status
GET  /api/auth/csrf
POST /api/auth/logout
GET  /api/youtube/auth-url
GET  /api/youtube/callback
```

### YouTube

```text
GET /api/youtube/channel
GET /api/youtube/videos
```

### Persistent playlists

```text
GET    /api/playlists
POST   /api/playlists
POST   /api/playlists/{playlist_id}/items
DELETE /api/playlists/{playlist_id}
```

### Streams

```text
GET  /api/streams
POST /api/streams
POST /api/streams/{stream_id}/start
POST /api/streams/{stream_id}/stop
GET  /api/streams/{stream_id}/status
GET  /api/streams/{stream_id}/logs
```

### Analytics

```text
GET /api/analytics
```

### Scheduling

```text
GET  /api/schedules
POST /api/schedules
POST /api/schedules/{schedule_id}/toggle
```

Interactive API docs:

```text
https://YOUR-BACKEND-DOMAIN/docs
```

## Authorized media

Recommended production media pipeline:

```text
Original / authorized file
        ↓
Object Storage / CDN
        ↓
Controlled media URL
        ↓
LoopLive playlist
        ↓
FFmpeg
        ↓
YouTube RTMPS
```

Do not enter third-party YouTube watch URLs as media source URLs unless you independently have the rights and a permitted source for that content.

## YouTube Live lifecycle

```text
liveBroadcasts.insert
        ↓
liveStreams.insert
        ↓
liveBroadcasts.bind
        ↓
FFmpeg → RTMPS
        ↓
liveBroadcasts.transition → live
        ↓
liveBroadcasts.transition → complete
```

Stream keys stay server-side and are never returned to the frontend.

## Production deployment

### Frontend

Deploy the Next.js application to Netlify and configure:

```env
NEXT_PUBLIC_API_BASE_URL=https://YOUR-BACKEND-DOMAIN
```

### Backend

Use a persistent VM/container/VPS capable of running FFmpeg continuously. Do not run FFmpeg inside Netlify Functions or another short-lived serverless function.

### V1 scaling path

For a larger production workload:

```text
Next.js / Netlify
        ↓
FastAPI
        ↓
PostgreSQL
        ↓
Redis / Job Queue
        ↓
Dedicated FFmpeg Workers
        ↓
Object Storage/CDN
        ↓
YouTube Live
```

## Security

- OAuth state is signed and expires quickly.
- Session cookies are HTTP-only and signed.
- CSRF token is required for browser state-changing requests.
- YouTube credentials are encrypted at rest.
- CORS is configurable and should be restricted to the production frontend.
- Stream keys remain backend-only.
- Never commit `.env`, OAuth secrets, refresh tokens or stream keys.

## V1 status

**Production-oriented V1 implementation pushed to the repository.**

The V1 code is intended for a controlled pilot on a persistent backend. Before high-scale multi-instance deployment, migrate persistence to PostgreSQL and worker execution to a distributed job queue.
