import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    cors_origins: list[str]
    frontend_url: str
    max_streams_per_pilot: int
    google_client_id: str
    google_client_secret: str
    youtube_redirect_uri: str
    database_url: str
    session_secret: str
    encryption_key: str
    session_max_age: int
    scheduler_interval: int

    @property
    def youtube_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.youtube_redirect_uri)

    @property
    def production_secrets_configured(self) -> bool:
        return len(self.session_secret) >= 32 and bool(self.encryption_key)

settings = Settings(
    cors_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if x.strip()],
    frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
    max_streams_per_pilot=int(os.getenv("MAX_STREAMS_PER_PILOT", "2")),
    google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    youtube_redirect_uri=os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/youtube/callback"),
    database_url=os.getenv("DATABASE_URL", "sqlite:///looplive.db"),
    session_secret=os.getenv("SESSION_SECRET", ""),
    encryption_key=os.getenv("ENCRYPTION_KEY", ""),
    session_max_age=int(os.getenv("SESSION_MAX_AGE", "604800")),
    scheduler_interval=int(os.getenv("SCHEDULER_INTERVAL", "15")),
)
