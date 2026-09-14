CREATE TABLE IF NOT EXISTS youtube_accounts (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  channel_id TEXT,
  channel_title TEXT,
  encrypted_refresh_token TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS videos (
  id UUID PRIMARY KEY,
  youtube_account_id UUID NOT NULL REFERENCES youtube_accounts(id) ON DELETE CASCADE,
  youtube_video_id TEXT NOT NULL,
  title TEXT NOT NULL,
  duration_seconds INTEGER,
  source_uri TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS streams (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  youtube_account_id UUID REFERENCES youtube_accounts(id),
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready',
  youtube_broadcast_id TEXT,
  youtube_stream_id TEXT,
  loop_enabled BOOLEAN NOT NULL DEFAULT true,
  quality TEXT NOT NULL DEFAULT '1080p',
  started_at TIMESTAMPTZ,
  stopped_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stream_jobs (
  id UUID PRIMARY KEY,
  stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  worker_id TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_streams_user ON streams(user_id);
CREATE INDEX IF NOT EXISTS idx_stream_jobs_status ON stream_jobs(status);
