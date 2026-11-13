import re
from pathlib import Path

import numpy as np
import soundfile as sf

from .core import ROOT, config, file_signature, load, save, signature, subtitles


def chunks(text, limit=210):
    sentences=re.split(r"(?<=[.!?])\s+",text.strip());result=[]
    for sentence in sentences:
        words=sentence.split();current=[]
        for word in words:
            if current and len(" ".join(current+[word]))>limit:
                result.append(" ".join(current));current=[]
            current.append(word)
        if current:result.append(" ".join(current))
    return result


def caption_groups(text, start, end):
    words=text.split();groups=[];current=[]
    for word in words:
        if current and (len(current)>=8 or len(" ".join(current+[word]))>66):
            groups.append(current);current=[]
        current.append(word)
    if current:groups.append(current)
    count=sum(len(g) for g in groups);offset=0;out=[]
    for group in groups:
        a=start+(end-start)*offset/count;offset+=len(group);b=start+(end-start)*offset/count
        text=" ".join(group)
        if len(text)>42:
            middle=min(range(1,len(group)),key=lambda i:abs(len(" ".join(group[:i]))-len(text)/2)) if len(group)>1 else 1
            text=" ".join(group[:middle])+"\n"+" ".join(group[middle:])
        out.append({"start":a,"end":b,"text":text})
    return out


def narrate(folder, project, progress=print):
    c=config(project);model=ROOT/"models"/"kokoro-v1.0.onnx";voices=ROOT/"models"/"voices-v1.0.bin"
    if not model.is_file() or not voices.is_file():raise ValueError("Kokoro model files missing. Run python -m studio models, then resume.")
    try:from kokoro_onnx import Kokoro
    except ImportError as exc:raise ValueError('Install the voice extra: python -m pip install -e ".[voice]"') from exc
    cache_path=folder/"voice-cache.json";cache=load(cache_path) if cache_path.exists() else {};tts=None
    model_info=[(f.name,f.stat().st_size,f.stat().st_mtime_ns) for f in (model,voices)]
    for scene in project["scenes"]:
        key=str(scene["id"]);dest=folder/"audio"/f"{scene['id']:03}.wav"
        expected=signature(scene["narration"],c["voice"],c["speed"],model_info)
        if dest.is_file() and cache.get(key,{}).get("signature")==expected and cache[key].get("audio_sha256")==file_signature(dest):
            progress(f"Voice {key}: unchanged; reused");continue
        if tts is None:
            progress("Loading local Kokoro narration on CPU…");tts=Kokoro(str(model),str(voices))
            if c["voice"] not in tts.get_voices():raise ValueError("Configured voice is unavailable")
        progress(f"Narrating scene {key}/{len(project['scenes'])}…")
        parts=[];timings=[];cursor=0;rate=None
        for text in chunks(scene["narration"]):
            audio,sr=tts.create(text,voice=c["voice"],speed=c["speed"],lang="en-gb" if c["voice"].startswith("b") else "en-us")
            if rate and sr!=rate:raise ValueError("Narrator changed sample rate")
            rate=sr;audio=np.asarray(audio,dtype=np.float32).reshape(-1)
            if not len(audio) or not np.isfinite(audio).all():raise ValueError("Narrator returned invalid audio")
            # De-click joins, preserve natural pauses and intonation inside chunks.
            fade=min(int(sr*.006),len(audio)//2)
            if fade:
                audio[:fade]*=np.linspace(0,1,fade);audio[-fade:]*=np.linspace(1,0,fade)
            length=len(audio)/sr;timings.extend(caption_groups(text,cursor,cursor+length));cursor+=length+.11
            parts.extend([audio,np.zeros(round(sr*.11),dtype=np.float32)])
        joined=np.concatenate(parts);peak=float(np.max(np.abs(joined)))
        if peak<.002:raise ValueError("Narration is effectively silent")
        if peak>.98:joined*=.98/peak
        dest.parent.mkdir(parents=True,exist_ok=True);sf.write(dest,joined,rate,subtype="PCM_16")
        cache[key]={"signature":expected,"audio_sha256":file_signature(dest),"captions":timings,"voice":c["voice"],"method":"local Kokoro"};save(cache_path,cache)


def assemble(folder, project):
    cache=load(folder/"voice-cache.json") if (folder/"voice-cache.json").exists() else {}
    output=[];segments=[];timeline=[];cursor=0;rate=None
    for scene in project["scenes"]:
        path=folder/"audio"/f"{scene['id']:03}.wav"
        if not path.is_file():raise ValueError(f"Missing scene narration: {path.name}")
        data,sr=sf.read(path,dtype="float32",always_2d=True)
        data=data.mean(axis=1)
        if not len(data) or not np.isfinite(data).all() or np.max(np.abs(data))<.002:raise ValueError(f"Scene {scene['id']} has empty/silent narration")
        if rate and sr!=rate:raise ValueError("Scene sample rates differ; resample imported audio first")
        rate=sr;length=len(data)/sr
        if length>90:raise ValueError("Scene narration exceeds 90 seconds; split the scene")
        pause=.18 if scene is not project["scenes"][-1] else .6
        output.extend([data,np.zeros(round(sr*pause),dtype=np.float32)])
        timeline.append({"id":scene["id"],"start":cursor,"end":cursor+length+pause,"speech_end":cursor+length})
        entry=cache.get(str(scene["id"]),{})
        timings=entry.get("captions") if entry.get("audio_sha256")==file_signature(path) else None
        if not timings:timings=caption_groups(scene["narration"],0,length)
        segments.extend({"text":t["text"],"start":cursor+t["start"],"end":cursor+min(t["end"],length)} for t in timings)
        cursor+=length+pause
    joined=np.concatenate(output);sf.write(folder/"narration.wav",joined,rate,subtype="PCM_16")
    (folder/"captions.srt").write_text(subtitles(segments),encoding="utf-8")
    save(folder/"timeline.json",{"scenes":timeline,"duration":cursor,"caption_timing":"Speech-chunk boundaries; within-chunk caption groups are estimated, not forced-aligned. Review before publishing."})
    return timeline
