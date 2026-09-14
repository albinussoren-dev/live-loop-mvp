FROM linuxserver/ffmpeg:latest
WORKDIR /worker
COPY loop-worker.sh /worker/loop-worker.sh
RUN chmod +x /worker/loop-worker.sh
ENTRYPOINT ["/worker/loop-worker.sh"]
