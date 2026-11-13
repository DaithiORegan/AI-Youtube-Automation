import json
import mimetypes
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .core import ROOT, load, save


def make_server(port=8787, projects=None):
    projects=Path(projects or ROOT/"projects").resolve();projects.mkdir(parents=True,exist_ok=True)
    web=Path(__file__).parent/"web";pool=ThreadPoolExecutor(max_workers=1);lock=threading.Lock()
    job={"running":False,"logs":[],"project":None,"error":None}
    def log(message):
        with lock:job["logs"]=(job["logs"]+[str(message)])[-150:]
    def execute(action,body):
        try:
            from .production import pipeline
            if action in ("create","pilot"):
                from .local_ai import create
                key=time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:6]
                with lock:job["project"]=key
                if action=="pilot":
                    from .production import copy_pilot
                    copy_pilot(projects/key);log("Loaded the prepared original pilot. Ollama is not needed for this story.")
                else:
                    p=create(body["topic"],body["seconds"],{"voice":body.get("voice","af_heart"),"checkpoint":body.get("checkpoint","sd_xl_base_1.0.safetensors")},log)
                    save(projects/key/"project.json",p)
            else:key=body["project"]
            pipeline(projects/key/"project.json",progress=log)
        except Exception as exc:
            with lock:job["error"]=str(exc)[-1800:]
            log("Stopped: "+str(exc))
        finally:
            with lock:job["running"]=False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,body,mime="application/json"):
            if not isinstance(body,(str,bytes)):body=json.dumps(body)
            if isinstance(body,str):body=body.encode()
            self.send_response(status);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(body)
        def host_ok(self):
            return self.headers.get("Host","") in (f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}")
        def do_GET(self):
            if not self.host_ok():return self.respond(400,{"error":"Invalid host"})
            path=urlsplit(self.path).path
            try:
                if path=="/api/status":
                    with lock:return self.respond(200,dict(job))
                if path=="/api/doctor":
                    from .production import doctor
                    return self.respond(200,doctor())
                if path=="/api/projects":
                    result=[]
                    for p in sorted(projects.glob("*/project.json"),reverse=True)[:40]:
                        try:
                            project=load(p);status=load(p.parent/"status.json") if (p.parent/"status.json").exists() else {"state":"planned"}
                            result.append({"id":p.parent.name,"title":project["title"],"scenes":len(project["scenes"]),"status":status,"review":(p.parent/"review.html").exists(),"final":(p.parent/"final.mp4").exists()})
                        except (ValueError,OSError,KeyError):continue
                    return self.respond(200,result)
                if path.startswith("/projects/"):
                    relative=unquote(path.removeprefix("/projects/"));file=(projects/relative).resolve()
                    if not file.is_relative_to(projects) or file.suffix.lower() not in (".html",".png",".jpg",".mp4",".wav",".srt",".vtt",".json",".txt") or not file.is_file():return self.respond(404,{"error":"Not found"})
                    # Stream large video masters instead of loading them into RAM.
                    size=file.stat().st_size;start,end=0,size-1;status=200
                    if self.headers.get("Range"):
                        import re
                        match=re.fullmatch(r"bytes=(\d+)-(\d*)",self.headers["Range"])
                        if not match:return self.respond(416,{"error":"Unsupported range"})
                        start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
                        if start>end:return self.respond(416,{"error":"Range out of bounds"})
                        status=206
                    self.send_response(status);self.send_header("Content-Type",mimetypes.guess_type(file.name)[0] or "application/octet-stream");self.send_header("Accept-Ranges","bytes");self.send_header("Content-Length",str(end-start+1));self.send_header("X-Content-Type-Options","nosniff")
                    if status==206:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    with file.open("rb") as f:
                        f.seek(start);remaining=end-start+1
                        while remaining>0:
                            data=f.read(min(1024*1024,remaining))
                            if not data:break
                            self.wfile.write(data);remaining-=len(data)
                    return
                filename={"/":"index.html","/app.js":"app.js","/style.css":"style.css"}.get(path)
                if filename:
                    file=web/filename
                    return self.respond(200,file.read_bytes(),mimetypes.guess_type(filename)[0] or "text/plain")
                return self.respond(404,{"error":"Not found"})
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as exc:return self.respond(500,{"error":str(exc)[:1000]})
        def do_POST(self):
            if not self.host_ok():return self.respond(400,{"error":"Invalid host"})
            if self.headers.get("X-Storyforge")!="1" or self.headers.get("Origin",f"http://{self.headers['Host']}")!=f"http://{self.headers['Host']}":return self.respond(403,{"error":"Cross-origin request blocked"})
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=128000:return self.respond(413,{"error":"Invalid body size"})
                body=json.loads(self.rfile.read(size));action=urlsplit(self.path).path.removeprefix("/api/")
                if not isinstance(body,dict):raise ValueError("Expected a JSON object")
                if action=="create":
                    if not isinstance(body.get("topic"),str) or not 8<=len(body["topic"])<=800:raise ValueError("Premise must be 8–800 characters")
                    if not isinstance(body.get("seconds"),int) or not 30<=body["seconds"]<=360:raise ValueError("Duration must be 30–360 seconds")
                elif action=="pilot":pass
                elif action in ("resume","approve"):
                    import re
                    key=body.get("project","")
                    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}",key) or not (projects/key/"project.json").is_file():raise ValueError("Project not found")
                else:return self.respond(404,{"error":"Unknown action"})
                with lock:
                    if job["running"]:return self.respond(409,{"error":"One production at a time protects GPU memory; wait for the current job"})
                    if action=="approve":
                        from .production import approve
                        result=approve(projects/key,load(projects/key/"project.json"),body.get("checks",{}))
                        return self.respond(200,result)
                    job.update({"running":True,"logs":[],"error":None,"project":body.get("project")})
                pool.submit(execute,action,body)
                return self.respond(202,{"queued":True})
            except (ValueError,KeyError,TypeError) as exc:return self.respond(422,{"error":str(exc)[:1000]})
            except Exception as exc:return self.respond(500,{"error":str(exc)[:1000]})
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler);server.pool=pool
    return server


def serve(port=8787,open_browser=True):
    server=make_server(port);url=f"http://127.0.0.1:{server.server_port}"
    print("Storyforge studio:",url,flush=True)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    finally:server.server_close();server.pool.shutdown(wait=False,cancel_futures=True)
