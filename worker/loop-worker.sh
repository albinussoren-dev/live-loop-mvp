#!/bin/sh
set -eu

: "${INPUT_FILE:?Set INPUT_FILE to an authorized local media file}"
: "${YOUTUBE_RTMP_URL:?Set YOUTUBE_RTMP_URL to the authorized YouTube RTMPS ingest URL}"

# The worker intentionally accepts a local/authorized media source rather than
# scraping or downloading arbitrary YouTube watch URLs.
exec ffmpeg -hide_banner -loglevel warning \
  -re -stream_loop -1 -i "$INPUT_FILE" \
  -c:v libx264 -preset veryfast -b:v "${VIDEO_BITRATE:-4500k}" -maxrate "${VIDEO_MAXRATE:-5000k}" -bufsize "${VIDEO_BUFSIZE:-10000k}" \
  -pix_fmt yuv420p -g 60 \
  -c:a aac -b:a "${AUDIO_BITRATE:-128k}" -ar 44100 \
  -f flv "$YOUTUBE_RTMP_URL"
