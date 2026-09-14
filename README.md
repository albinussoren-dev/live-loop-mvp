# LoopLive MVP

LoopLive is a 50-user pilot SaaS for creating continuous YouTube Live streams from **authorized media sources**. The platform connects a user's Google/YouTube account, loads the channel's uploaded videos, builds a playlist, creates a YouTube Live broadcast, sends media to YouTube over RTMPS, and keeps the FFmpeg worker running with automatic restart.

> **Important:** LoopLive does not download or scrape arbitrary YouTube watch URLs. A YouTube `videoId` identifies a video but does not provide a downloadable media URL through the YouTube Data API. The MVP therefore expects a permitted media source URL for each selected video (for example, media owned by the user and stored in an accessible object-storage/CDN location).

## Current MVP flow

```text
Google Login
    ↓
YouTube Channel Connect
    ↓
Load Channel Videos
    ↓
Select Videos / Build Playlist
    ↓
Provide Permitted Media Source URLs
    ↓
Create YouTube Broadcast + Live Stream
    ↓
Bind Broadcast to Stream
    ↓
FFmpeg → RTMPS → YouTube
    ↓
Auto-restart on worker failure
    ↓
Live Status + Logs + Basic Analytics
```

## Features implemented

### Google / YouTube
- Google OAuth authorization flow
- YouTube channel connection
- Access to the authenticated channel
- Channel uploaded-video listing through the channel uploads playlist
- YouTube Live broadcast creation
- YouTube Live stream creation
- Broadcast ↔ stream binding
- Broadcast transition to `live` and `complete`

### Streaming
- FFmpeg-based streaming worker
- RTMP/RTMPS output to YouTube
- Continuous media looping
- Multiple media sources through an FFmpeg concat list
- Automatic worker restart after FFmpeg exits
- FFmpeg stderr captured into application logs

### Dashboard / API
- Connected-channel status
- Video library loading
- Multi-video playlist selection
- Permitted media-source URL mapping
- Create/start live stream
- Stop/complete stream action
- Stream status
- Stream logs
- Basic analytics endpoint
- SQLite persistence for the MVP

## Repository structure

```text
live-loop-mvp/
├── app/
│   ├── globals.css
│   └── page.tsx
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── settings.py
│   │   ├── worker.py
│   │   └── youtube.py
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
├── package.json
└── README.md
```

## Architecture

```text
                 ┌─────────────────────┐
                 │   Next.js Frontend   │
                 │      Netlify         │
                 └──────────┬──────────┘
                            │ REST API
                            ▼
                 ┌─────────────────────┐
                 │     FastAPI API      │
                 │   OAuth + YouTube    │
                 └──────────┬──────────┘
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
          ┌──────────────┐    ┌──────────────┐
          │   SQLite DB  │    │ FFmpeg Worker│
          │ MVP storage  │    │  RTMPS out   │
          └──────────────┘    └───────┬──────┘
                                      │
                                      ▼
                              ┌──────────────┐
                              │ YouTube Live │
                              └──────────────┘
```

The frontend is suitable for Netlify. **FFmpeg must run on a persistent backend host**; Netlify is not a persistent FFmpeg worker environment.

## Requirements

- Node.js 20+
- npm
- Python 3.12+
- FFmpeg
- Google Cloud project
- YouTube Data API v3 enabled
- YouTube Live Streaming API enabled
- Google OAuth Web application credentials

Docker can be used to run the backend with FFmpeg included.

## Google Cloud / YouTube setup

1. Create or select a Google Cloud project.
2. Enable:
   - YouTube Data API v3
   - YouTube Live Streaming API
3. Configure the OAuth consent screen.
4. Create an **OAuth Client ID → Web application**.
5. Add the backend callback URL to **Authorized redirect URIs**.
6. Copy the client ID and client secret into the backend environment.

For local development, the default callback is:

```text
http://localhost:8000/api/youtube/callback
```

The application uses YouTube OAuth scopes for channel/video access and live-stream management. OAuth credentials and refresh tokens must be kept secret.

## Environment variables

Copy `.env.example` to `.env` and configure:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000
MAX_STREAMS_PER_PILOT=2
DATABASE_URL=sqlite:///looplive.db

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
YOUTUBE_REDIRECT_URI=http://localhost:8000/api/youtube/callback
```

For production, use a real secret manager and encrypted token storage rather than committing secrets to Git.

## Run frontend locally

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_API_BASE_URL` and calls the FastAPI backend.

## Run backend locally

From the `backend` directory:

```bash
python -m venv .venv
```

### Linux / macOS

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend health check:

```text
http://localhost:8000/health
```

## Run backend with Docker

```bash
docker compose up --build
```

The API will be available on port `8000`.

The Docker image installs FFmpeg, so the streaming worker can be launched by the FastAPI application.

## API endpoints

### System

```text
GET  /health
```

### YouTube

```text
GET  /api/youtube/auth-url
GET  /api/youtube/callback
GET  /api/youtube/channel
GET  /api/youtube/videos
```

### Streams

```text
GET  /api/streams
POST /api/streams
POST /api/streams/{stream_id}/start
POST /api/streams/{stream_id}/stop
GET  /api/streams/{stream_id}/logs
```

### Analytics

```text
GET /api/analytics
```

Interactive FastAPI documentation is available at:

```text
http://localhost:8000/docs
```

## Authorized media workflow

The MVP intentionally separates **YouTube metadata** from the **actual media source**.

When the dashboard loads a user's uploaded videos, it receives metadata such as:

- video ID
- title
- description
- published time
- thumbnail

The YouTube Data API does not return a raw downloadable MP4/HLS media URL for a normal YouTube watch video. Therefore the playlist builder accepts a corresponding **permitted media source URL** for each selected item.

Recommended production flow:

```text
Original / authorized media file
        ↓
Object Storage (S3 / GCS / compatible)
        ↓
Signed or controlled media URL
        ↓
LoopLive FFmpeg worker
        ↓
YouTube RTMPS ingest
```

Only stream media that you own or are explicitly authorized to use.

## YouTube Live lifecycle

LoopLive follows the standard YouTube Live workflow:

```text
liveBroadcasts.insert
        ↓
liveStreams.insert
        ↓
liveBroadcasts.bind
        ↓
FFmpeg sends RTMPS
        ↓
liveBroadcasts.transition → live
        ↓
liveBroadcasts.transition → complete
```

The stream's ingestion address and stream key are used by the backend worker. **Never expose stream keys in frontend logs, public repositories, screenshots, or client-side code.**

## Pilot limits

The MVP currently defaults to:

```env
MAX_STREAMS_PER_PILOT=2
```

This is intentionally conservative for the pilot. It is not a complete production multi-tenant quota system yet.

## Production gaps / next phase

The current implementation is an MVP/pilot foundation, not a finished production SaaS. Before supporting a real 50-user workload, the following should be completed:

- PostgreSQL instead of SQLite
- Redis-backed worker/job queue
- Separate worker service/containers
- Proper multi-tenant user accounts and sessions
- Secure OAuth `state` validation / CSRF protection
- Encrypted refresh-token storage
- Token refresh persistence
- Reliable worker PID/process lifecycle and graceful stop
- Persistent playlists and reusable schedules
- Object-storage media ingestion and validation
- Per-user stream quotas and usage metering
- Real YouTube analytics integration
- Rich logs and live worker health monitoring
- Scheduling and timezone handling
- Retry/backoff policies
- Billing/subscriptions
- Admin dashboard
- Production monitoring and alerting
- HTTPS and production CORS configuration

## Deployment

### Frontend

The Next.js frontend can be deployed to Netlify. Set:

```env
NEXT_PUBLIC_API_BASE_URL=https://YOUR-BACKEND-DOMAIN
```

The deployed frontend must be able to reach the backend over HTTPS.

### Backend

Deploy FastAPI + FFmpeg on a persistent compute service such as a VPS, VM, container platform, or managed server environment that permits long-running FFmpeg processes.

Do **not** deploy the FFmpeg worker as a Netlify Function or other short-lived serverless function.

## Security checklist

Before production:

- [ ] Never commit `.env` or OAuth secrets
- [ ] Encrypt refresh tokens at rest
- [ ] Implement OAuth state validation
- [ ] Add real user authentication/session handling
- [ ] Isolate each user's YouTube credentials
- [ ] Protect stream keys
- [ ] Validate/allowlist media source URLs
- [ ] Use HTTPS everywhere
- [ ] Restrict CORS to trusted frontend domains
- [ ] Add rate limiting
- [ ] Add worker resource limits
- [ ] Add audit logs

## Compliance

LoopLive should only be used with media and accounts the operator is authorized to use. Follow YouTube's Terms of Service, API Services Terms, copyright rules, and live-streaming requirements.

Do not build features that download, scrape, rebroadcast, or otherwise process third-party YouTube content without the required rights or authorization.

## Status

**MVP foundation implemented.**

The repository contains the working application structure for Google/YouTube OAuth, channel/video retrieval, YouTube Live lifecycle, FFmpeg looping, RTMPS output, auto-restart, logs, basic analytics, and a connected dashboard. Production hardening and true multi-user scaling remain for the next phase.
