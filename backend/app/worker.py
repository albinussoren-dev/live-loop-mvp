import os, sqlite3, subprocess, time
from datetime import datetime, timezone
DB=os.getenv('DATABASE_URL','sqlite:///looplive.db').replace('sqlite:///','')

def log(sid,level,msg):
 c=sqlite3.connect(DB); c.execute('INSERT INTO logs(stream_id,level,message,created_at) VALUES(?,?,?,?)',(sid,level,msg,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()

def run_stream(sid,source,ingest,key,loop=True):
 while True:
  cmd=['ffmpeg','-hide_banner','-loglevel','warning','-re','-stream_loop','-1' if loop else '0','-i',source,'-c:v','libx264','-preset','veryfast','-tune','zerolatency','-b:v','4500k','-maxrate','4500k','-bufsize','9000k','-pix_fmt','yuv420p','-r','30','-g','60','-c:a','aac','-b:a','128k','-ar','44100','-f','flv',f'{ingest}/{key}']
  log(sid,'info','FFmpeg worker started')
  p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
  for line in p.stderr:
   if line.strip(): log(sid,'info',line.strip()[-1000:])
  code=p.wait(); log(sid,'error',f'FFmpeg exited with code {code}; restarting in 5s')
  if not loop: break
  time.sleep(5)

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser(); ap.add_argument('--stream-id',required=True); ap.add_argument('--source',required=True); ap.add_argument('--ingest',required=True); ap.add_argument('--key',required=True); ap.add_argument('--no-loop',action='store_true'); a=ap.parse_args(); run_stream(a.stream_id,a.source,a.ingest,a.key,not a.no_loop)
