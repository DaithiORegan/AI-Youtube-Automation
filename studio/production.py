import html
import importlib.util
import json
import shutil
import time
from pathlib import Path

from .core import ROOT, DEFAULTS, config, file_signature, load, project_paths, run, save, signature
from .local_ai import local_session


def doctor(settings=None):
    c={**DEFAULTS,**(settings or {})};checks=[]
    def add(name,ok,detail,required=True):checks.append({"name":name,"ok":bool(ok),"detail":detail,"required":required})
    for binary in ("ffmpeg","ffprobe"):
        add(binary,shutil.which(binary),shutil.which(binary) or "Install FFmpeg and reopen your terminal")
    if shutil.which("ffmpeg"):
        filters=run(["ffmpeg","-hide_banner","-filters"],30).stdout
        for name in ("zoompan","loudnorm","sidechaincompress","subtitles"):add("FFmpeg "+name,name in filters,"Required video/audio filter")
    add("Kokoro package",importlib.util.find_spec("kokoro_onnx") is not None,'Install: python -m pip install -e ".[voice]"')
    for name in ("kokoro-v1.0.onnx","voices-v1.0.bin"):
        path=ROOT/"models"/name;add(name,path.is_file(),str(path)+" — run python -m studio models if missing")
    for name,url,route in [("Ollama",c["ollama_url"],"/api/tags"),("ComfyUI",c["comfy_url"],"/object_info/CheckpointLoaderSimple")]:
        try:
            session=local_session(url);r=session.get(url+route,timeout=4);r.raise_for_status();data=r.json();add(name,True,url)
            if name=="Ollama":
                names=[m.get("name","") for m in data.get("models",[])];add("Story model",c["model"] in names or c["model"]+":latest" in names,"Configured "+c["model"]+"; available: "+", ".join(names))
            else:
                names=data.get("CheckpointLoaderSimple",{}).get("input",{}).get("required",{}).get("ckpt_name",[[]])[0]
                add("Illustration checkpoint",c["checkpoint"] in names,"Configured "+c["checkpoint"]+"; available: "+", ".join(names[:12]))
        except Exception as exc:add(name,False,f"Not ready at {url}: {type(exc).__name__}")
    free=shutil.disk_usage(ROOT).free/1024**3;add("Disk space",free>10,f"{free:.1f} GiB free; allow 20–30 GiB for first-time downloads and projects",False)
    if shutil.which("nvidia-smi"):
        try:add("GPU",True,run(["nvidia-smi","--query-gpu=name,memory.total","--format=csv,noheader"],15).stdout.strip(),False)
        except Exception:add("GPU",False,"nvidia-smi failed; check NVIDIA driver",False)
    else:add("GPU",False,"No NVIDIA GPU detected in this environment; local ComfyUI generation was not verified here",False)
    return {"ready":all(c["ok"] for c in checks if c["required"]),"checks":checks,"cost":"No paid API calls; local hardware/electricity and downloads still apply."}


def download_models(progress=print):
    import requests
    folder=ROOT/"models";folder.mkdir(exist_ok=True);records=[]
    for name,minimum in [("kokoro-v1.0.onnx",100*1024*1024),("voices-v1.0.bin",1024*1024)]:
        dest=folder/name;url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"+name
        if not dest.exists():
            progress("Downloading free local voice model: "+name);temp=dest.with_suffix(dest.suffix+".part");size=0
            try:
                with requests.get(url,stream=True,timeout=(15,60)) as r:
                    r.raise_for_status()
                    with temp.open("wb") as f:
                        for chunk in r.iter_content(1024*1024):
                            size+=len(chunk)
                            if size>600*1024*1024:raise ValueError("Model download exceeds 600 MiB")
                            f.write(chunk)
                if size<minimum:raise ValueError("Model download is unexpectedly small")
                temp.replace(dest)
            finally:
                if temp.exists():temp.unlink()
        if dest.stat().st_size<minimum:raise ValueError("Existing model file is too small: "+name)
        records.append({"file":name,"source":url,"sha256":file_signature(dest)})
    save(folder/"download-provenance.json",records)
    return records


def current_inputs(folder, project):
    files=[folder/"project.json",folder/"final.mp4",folder/"captions.srt"]
    files += [folder/"art"/f"{s['id']:03}.png" for s in project["scenes"]]
    files += [folder/"audio"/f"{s['id']:03}.wav" for s in project["scenes"]]
    for optional in ("image-cache.json","voice-cache.json"):
        if (folder/optional).is_file():files.append(folder/optional)
    return signature({str(p.relative_to(folder)):file_signature(p) for p in files})


def copy_pilot(folder):
    dest=Path(folder)/"project.json"
    if dest.exists():raise ValueError("Pilot project already exists; resume it or choose another directory")
    save(dest,load(Path(__file__).parent/"data"/"first-film.json"))
    return dest


def package(folder, project):
    from .render import contact_sheet
    contact_sheet(folder,project)
    quality=load(folder/"quality.json") if (folder/"quality.json").exists() else None
    # Old masters must not be approved after changing scripts, images or audio.
    current=signature(project,{f"art/{s['id']:03}.png":file_signature(folder/"art"/f"{s['id']:03}.png") for s in project["scenes"] if (folder/"art"/f"{s['id']:03}.png").exists()},{f"audio/{s['id']:03}.wav":file_signature(folder/"audio"/f"{s['id']:03}.wav") for s in project["scenes"] if (folder/"audio"/f"{s['id']:03}.wav").exists()})
    desc=project.get("description",project["premise"])
    desc += "\n\nAn original fictional story, illustrated and narrated using local AI tools and edited as a story film. Characters and events are fictional."
    metadata={"title":project["title"][:100],"description":desc[:5000],"tags":["original fiction","illustrated story","what if story"],"privacy":"private","made_for_kids":"REVIEW_REQUIRED — animation alone does not decide the audience", "synthetic_media":"REVIEW_REQUIRED — disclose realistic synthetic people/events/places when applicable; obviously stylised fantasy may not require the label", "music_rights":config(project).get("music_rights",""),"auto_upload":False}
    save(folder/"upload-metadata.json",metadata)
    (folder/"script.txt").write_text("\n\n".join(s["narration"] for s in project["scenes"]),encoding="utf-8")
    from .core import scene_prompt
    (folder/"art-prompts.txt").write_text("\n\n".join(f"SCENE {s['id']}\n{scene_prompt(project,s)}" for s in project["scenes"]),encoding="utf-8")
    save(folder/"package-state.json",{"editorial_inputs":current,"technical_pass":bool(quality and quality.get("technical_pass")),"generated_at":time.time()})
    e=lambda value:html.escape(str(value))
    scenes="".join(f"<article><img src='art/{s['id']:03}.png' alt='Scene {s['id']}' loading='lazy'><div><small>{s['id']:02} / {e(s['beat'])} / {e(s.get('camera','push'))}</small><h3>{e(s['narration'])}</h3><p>{e(s['image_prompt'])}</p></div></article>" for s in project["scenes"])
    page=f"""<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{e(project['title'])} — review</title><style>body{{font:16px system-ui;background:#111923;color:#eaf0f5;max-width:1200px;margin:40px auto;padding:0 22px}}h1{{font-size:40px;letter-spacing:-1px}}p,li{{color:#a4b7c8;line-height:1.7}}article{{display:grid;grid-template-columns:42% 1fr;background:#1b2838;border:1px solid #2d4055;border-radius:12px;overflow:hidden;margin:20px 0}}article img{{width:100%;height:100%;object-fit:cover}}article div{{padding:22px}}small{{color:#c4efa0}}video{{width:100%;border-radius:12px}}a{{color:#c4efa0}}.notice{{padding:22px;border:1px solid #405a72;border-radius:12px}}@media(max-width:700px){{article{{display:block}}h1{{font-size:28px}}}}</style><small>STORYFORGE / ORIGINAL FICTION / HUMAN REVIEW</small><h1>{e(project['title'])}</h1><p>{e(project['premise'])}</p><div class='notice'>Review the complete video: story and ending, voice pronunciation, recurring character identity, hands/faces, unwanted generated text, crop and captions. Technical checks do not guarantee artistic quality, platform compliance or monetisation.</div><h2>{'Video master' if (folder/'final.mp4').exists() else 'Preview — not a final master'}</h2><video controls preload='metadata' src="{'final.mp4' if (folder/'final.mp4').exists() else 'preview.mp4'}"><track kind='subtitles' src='captions.vtt' srclang='en' label='English' default></video><p><a href='preview.mp4'>Preview</a> · <a href='captions.srt'>Captions</a> · <a href='upload-metadata.json'>Upload metadata</a> · <a href='contact-sheet.jpg'>Contact sheet</a></p><h2>Continuity and scene review</h2>{scenes}<h2>Publishing checklist</h2><ul><li>Watch/listen to the whole export and check captions; timings inside speech chunks are estimated.</li><li>Confirm model, voice and music rights and any third-party assets.</li><li>Choose the correct audience designation and synthetic-media disclosure in YouTube Studio.</li><li>Review originality and substance across the channel; avoid repetitive mass-produced episodes.</li><li>Upload privately first; check processing, copyright and playback before public release.</li></ul><p><a href='https://support.google.com/youtube/answer/14328491'>YouTube altered/synthetic content guidance</a> · <a href='https://support.google.com/youtube/answer/1311392'>YouTube monetisation policies</a></p></html>"""
    (folder/"review.html").write_text(page,encoding="utf-8")
    if (folder/"captions.srt").exists():
        import re
        srt=(folder/"captions.srt").read_text(encoding="utf-8")
        (folder/"captions.vtt").write_text("WEBVTT\n\n"+re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})",r"\1.\2",srt),encoding="utf-8")
    return folder/"review.html"


def approve(folder, project, checks):
    if project.get("technical_demo"):raise ValueError("The synthetic technical demo cannot be approved for publication")
    required=["watched_full_video","character_continuity","voice_and_captions","rights_reviewed","youtube_settings_reviewed"]
    if any(checks.get(k) is not True for k in required):raise ValueError("All five editorial review checks must be confirmed")
    if not (folder/"quality.json").is_file():raise ValueError("Render a final master first; previews cannot be approved")
    q=load(folder/"quality.json")
    if not q.get("technical_pass") or q.get("video_sha256")!=file_signature(folder/"final.mp4"):raise ValueError("Video has changed or technical checks failed")
    state=load(folder/"render-state.json") if (folder/"render-state.json").exists() else {}
    if state.get("project_signature")!=signature(project):raise ValueError("Project changed since rendering; render again before approval")
    expected={f"art/{s['id']:03}.png":file_signature(folder/"art"/f"{s['id']:03}.png") for s in project["scenes"]}
    expected.update({f"audio/{s['id']:03}.wav":file_signature(folder/"audio"/f"{s['id']:03}.wav") for s in project["scenes"]})
    if state.get("assets_signature")!=signature(expected):raise ValueError("Scene assets changed since rendering; render again")
    result={"approved_at":time.time(),"checks":checks,"input_signature":current_inputs(folder,project),"video_sha256":q["video_sha256"],"publication":"Not uploaded or published. Final upload settings remain the operator's responsibility."}
    save(folder/"approval.json",result);return result


def _pipeline(path, stages=("voice","images","render","package"), preview=False, progress=print):
    folder,p=project_paths(path)
    for stage in stages:
        save(folder/"status.json",{"stage":stage,"state":"running","updated_at":time.time()})
        try:
            progress(f"\n{stage.upper()} — {p['title']}")
            if stage=="voice":
                from .audio import narrate
                narrate(folder,p,progress)
            elif stage=="images":
                from .local_ai import images
                images(folder,p,progress)
            elif stage=="render":
                from .render import render
                render(folder,p,preview,progress)
                if not preview:
                    assets={f"art/{s['id']:03}.png":file_signature(folder/"art"/f"{s['id']:03}.png") for s in p["scenes"]}
                    assets.update({f"audio/{s['id']:03}.wav":file_signature(folder/"audio"/f"{s['id']:03}.wav") for s in p["scenes"]})
                    save(folder/"render-state.json",{"project_signature":signature(p),"assets_signature":signature(assets)})
            elif stage=="package":package(folder,p)
            else:raise ValueError("Unknown stage")
        except Exception as exc:
            save(folder/"status.json",{"stage":stage,"state":"failed","error":str(exc)[-1800:],"updated_at":time.time()});raise
    if "package" in stages:
        save(folder/"status.json",{"stage":"review","state":"ready_for_review","updated_at":time.time()})
        progress("Review package ready. Open review.html and watch the entire film before approving.")
    else:
        save(folder/"status.json",{"stage":stages[-1],"state":"stage_complete","updated_at":time.time()})
        progress("Requested stages complete. Continue the remaining stages or run package to create the review page.")


def pipeline(path, stages=("voice","images","render","package"), preview=False, progress=print):
    import os
    folder=Path(path).resolve().parent;lock=folder/".production.lock"
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:
        raise ValueError("Project is already locked by a production. If its process was forcibly closed, confirm it has stopped, then remove .production.lock and resume.") from exc
    try:
        with os.fdopen(fd,"w") as f:f.write(str(os.getpid()))
        return _pipeline(path,stages,preview,progress)
    finally:
        lock.unlink(missing_ok=True)
