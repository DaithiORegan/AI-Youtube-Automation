from __future__ import annotations
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE = "Original cinematic storybook illustration, expressive faces, elegant ink contours, painterly textured backgrounds, warm amber highlights against cool teal shadows, dramatic motivated lighting, thoughtful composition, clear silhouettes, no captions, no letters, no logos, no watermark."
DEFAULTS = {"ollama_url":"http://127.0.0.1:11434", "model":"qwen3:4b", "comfy_url":"http://127.0.0.1:8188", "checkpoint":"sd_xl_base_1.0.safetensors", "voice":"af_heart", "speed":1.0, "seed":41721, "image_width":1344, "image_height":768, "steps":24, "fps":30, "width":1920, "height":1080, "crf":18, "preset":"medium", "music":None, "music_rights":"", "checkpoint_rights_reviewed":False, "voice_rights_reviewed":False, "burn_captions":False}


def load(path):
    path=Path(path)
    if path.stat().st_size>5*1024*1024: raise ValueError("JSON input exceeds 5 MiB")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding="utf-8")
    temp.replace(path)


def signature(*values):
    return hashlib.sha256(json.dumps(values,sort_keys=True,default=str).encode()).hexdigest()


def file_signature(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, timeout=1800, cwd=None):
    result=subprocess.run([str(a) for a in args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,cwd=cwd)
    if result.returncode:
        raise RuntimeError(f"{Path(str(args[0])).name} failed:\n{result.stderr[-2500:]}")
    return result


def probe(path):
    return json.loads(run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",path],60).stdout)


def duration(path):
    return float(probe(path)["format"]["duration"])


def validate(project):
    if not isinstance(project,dict): raise ValueError("Project must be a JSON object")
    for name in ("title","premise","character_bible","style_bible"):
        if not isinstance(project.get(name),str) or not project[name].strip(): raise ValueError(f"Missing {name}")
    scenes=project.get("scenes")
    if not isinstance(scenes,list) or not 3<=len(scenes)<=100: raise ValueError("Provide 3–100 scenes")
    for i,s in enumerate(scenes,1):
        if s.get("id")!=i: raise ValueError("Scene IDs must be consecutive integers beginning at 1")
        for name in ("narration","image_prompt","beat"):
            if not isinstance(s.get(name),str) or not s[name].strip(): raise ValueError(f"Scene {i}: missing {name}")
        if not 3<=len(s["narration"].split())<=65: raise ValueError(f"Scene {i}: narration must contain 3–65 words")
        if len(s["image_prompt"])>2500: raise ValueError(f"Scene {i}: image prompt too long")
        if re.search(r"\[VERIFY\]|<think>|\[TODO\]",s["narration"],re.I): raise ValueError(f"Scene {i}: unresolved model output")
        if s.get("camera","push") not in ("push","pull","left","right"): raise ValueError("Unsupported camera move")
        if s.get("art_source","generated") not in ("generated","manual"): raise ValueError("Art source must be generated or manual")
    if scenes[0]["beat"]!="hook" or scenes[-1]["beat"]!="payoff": raise ValueError("Start with a hook and end with a payoff")
    if not any(s["beat"]=="reversal" for s in scenes): raise ValueError("Story needs a reversal with consequences")
    return project


def config(project):
    c={**DEFAULTS,**project.get("settings",{})}
    for key in ("image_width","image_height"):
        if not isinstance(c[key],int) or not 512<=c[key]<=1536 or c[key]%64: raise ValueError(f"Invalid {key}")
    if c["fps"] not in (24,25,30): raise ValueError("FPS must be 24, 25 or 30")
    if c["width"] not in (640,1280,1920) or c["height"] != c["width"]*9//16: raise ValueError("Use a 16:9 output at 640, 1280 or 1920 pixels wide")
    if not 1<=c["steps"]<=50 or not .75<=c["speed"]<=1.25: raise ValueError("Invalid steps or narration speed")
    if not 15<=c["crf"]<=28 or c["preset"] not in ("fast","medium","slow"): raise ValueError("Unsupported encoding settings")
    return c


def project_paths(path):
    path=Path(path).resolve()
    p=validate(load(path));config(p)
    return path.parent,p


def scene_prompt(project, scene):
    return "\n".join([project["style_bible"],"Character continuity reference: "+project["character_bible"],"Only depict the characters explicitly requested in this shot; do not illustrate the entire cast.","This specific shot: "+scene["image_prompt"],"Keep the established costume, face and proportions. No typography."])


def srt_time(seconds):
    ms=round(seconds*1000);s,ms=divmod(ms,1000);m,s=divmod(s,60);h,m=divmod(m,60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def subtitles(segments):
    lines=[]
    for i,s in enumerate(segments,1):
        text=s["text"].replace("\n"," ").replace("-->","→")
        lines.append(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{text}\n")
    return "\n".join(lines)
