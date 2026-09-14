"""Streaming worker design placeholder.

A production worker should consume an authorized media source and publish it to
YouTube Live over RTMPS using FFmpeg/GStreamer. Do not scrape or download
arbitrary YouTube videos. Only process media the account is authorized to use.
"""

from dataclasses import dataclass

@dataclass
class StreamJob:
    stream_id: str
    source_url: str
    rtmp_url: str


def build_ffmpeg_command(job: StreamJob) -> list[str]:
    """Return a safe looping FFmpeg command for an authorized local/media URL."""
    return [
        "ffmpeg", "-re", "-stream_loop", "-1", "-i", job.source_url,
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k",
        "-maxrate", "4500k", "-bufsize", "9000k", "-pix_fmt", "yuv420p",
        "-g", "60", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-f", "flv", job.rtmp_url,
    ]
