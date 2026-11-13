import json
import math
import re
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw, ImageFont

from .audio import assemble
from .core import config, duration, file_signature, load, probe, run, save, signature


def inspect_art(folder, project, preview=False):
    seen={};warnings=[]
    for s in project["scenes"]:
        path=folder/"art"/f"{s['id']:03}.png"
        if not path.is_file():raise ValueError(f"Scene {s['id']}: illustration missing. Run images or supply art/{s['id']:03}.png. A blank fallback will not be rendered.")
        with Image.open(path) as image:
            image.load()
            minimum=(320,180) if preview else (1024,576)
            if image.width<minimum[0] or image.height<minimum[1]:raise ValueError(f"Scene {s['id']}: illustration below {minimum[0]}×{minimum[1]}")
        digest=file_signature(path)
        if digest in seen:warnings.append(f"Scenes {seen[digest]} and {s['id']} use identical art; review repetition.")
        seen[digest]=s["id"]
    return warnings


def motion_filter(camera, frames, width, height, fps):
    progress=f"on/{max(1,frames-1)}"
    zoom=f"1.10-0.08*{progress}" if camera=="pull" else f"1.02+0.08*{progress}" if camera=="push" else "1.09"
    x=f"(iw-iw/zoom)*{progress}" if camera=="right" else f"(iw-iw/zoom)*(1-{progress})" if camera=="left" else "iw/2-iw/zoom/2"
    return f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase:flags=lanczos,crop={width*2}:{height*2},zoompan=z='{zoom}':x='{x}':y='ih/2-ih/zoom/2':d={frames}:s={width}x{height}:fps={fps},setsar=1,format=yuv420p"


def normalise_audio(folder, c, seconds, progress):
    source=folder/"narration.wav";mixed=folder/"mix.wav"
    if c.get("music"):
        music=Path(c["music"]).expanduser().resolve()
        if not music.is_file():raise ValueError("Configured music file does not exist")
        if not c.get("music_rights","").strip():raise ValueError("Record the music's licence/ownership in settings.music_rights before using it")
        fade=max(0,seconds-2)
        graph=f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v][side];[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.12,afade=t=in:d=1,afade=t=out:st={fade}:d=2[m];[m][side]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=350[d];[v][d]amix=inputs=2:duration=first:normalize=0[out]"
        run(["ffmpeg","-y","-v","error","-i",source,"-stream_loop","-1","-i",music,"-filter_complex",graph,"-map","[out]","-t",f"{seconds:.6f}","-c:a","pcm_s24le",mixed])
        source=mixed
    progress("Measuring and normalising narration mix (two-pass loudness)…")
    analysis=run(["ffmpeg","-hide_banner","-i",source,"-af","aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json","-f","null","-"])
    matches=re.findall(r"\{[^{}]*\}",analysis.stderr,re.S)
    if not matches:raise ValueError("FFmpeg did not return a loudness measurement")
    m=json.loads(matches[-1]);keys=["input_i","input_tp","input_lra","input_thresh","target_offset"]
    if not all(math.isfinite(float(m[k])) for k in keys):raise ValueError("Audio is silent or loudness measurement is invalid")
    filt=f"aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000"
    run(["ffmpeg","-y","-v","error","-i",source,"-af",filt,"-c:a","pcm_s24le",folder/"master.wav"])
    save(folder/"loudness.json",{"target_lufs":-16,"target_true_peak_dbtp":-1.5,"source_measurement":m})


def render(folder, project, preview=False, progress=print):
    c=config(project);warnings=inspect_art(folder,project,preview);timeline=assemble(folder,project)
    width,height=(640,360) if preview else (c["width"],c["height"]);fps=c["fps"]
    clips=folder/"cache"/("preview" if preview else "master");clips.mkdir(parents=True,exist_ok=True)
    for scene,timing in zip(project["scenes"],timeline):
        key=f"{scene['id']:03}";image=folder/"art"/(key+".png");clip=clips/(key+".mp4");stamp=clips/(key+".json")
        frames=math.ceil((timing["end"]-timing["start"])*fps)
        expected=signature(file_signature(image),frames,width,height,fps,scene.get("camera","push"),c["crf"],c["preset"])
        stored=load(stamp) if stamp.exists() else {}
        if clip.exists() and stored.get("signature")==expected and stored.get("clip_sha256")==file_signature(clip):
            progress(f"Shot {key}: unchanged; reused");continue
        progress(f"Animating shot {key}/{len(timeline)} at {width}×{height}…")
        filt=motion_filter(scene.get("camera","push"),frames,width,height,fps)
        run(["ffmpeg","-y","-v","error","-filter_threads","1","-i",image,"-vf",filt,"-frames:v",frames,"-an","-c:v","libx264","-threads","2","-preset","fast" if preview else c["preset"],"-crf",23 if preview else c["crf"],clip])
        save(stamp,{"signature":expected,"clip_sha256":file_signature(clip)})
    # Quantise narration pauses to rendered scene frame boundaries. Without this,
    # per-shot rounding would accumulate into a visible final sync error.
    import numpy as np
    import soundfile as sf
    source,sr=sf.read(folder/"narration.wav",dtype="float32");parts=[];offset=0;adjusted=[]
    for timing in timeline:
        a=round(timing["start"]*sr);b=round(timing["end"]*sr)
        data=source[a:b];frames=math.ceil((timing["end"]-timing["start"])*fps);samples=round(frames/fps*sr)
        parts.append(np.pad(data,(0,max(0,samples-len(data))))[:samples])
        adjusted.append({"id":timing["id"],"start":offset,"end":offset+samples/sr});offset+=samples/sr
    sf.write(folder/"narration.wav",np.concatenate(parts),sr,subtype="PCM_16")
    # Shift caption timings by cumulative frame padding, preserving each speech interval.
    from .core import subtitles
    from .audio import caption_groups
    cache=load(folder/"voice-cache.json") if (folder/"voice-cache.json").exists() else {};segments=[]
    for scene,old,new in zip(project["scenes"],timeline,adjusted):
        audio=folder/"audio"/f"{scene['id']:03}.wav";entry=cache.get(str(scene["id"]),{})
        ts=entry.get("captions") if entry.get("audio_sha256")==file_signature(audio) else None
        ts=ts or caption_groups(scene["narration"],0,old["speech_end"]-old["start"])
        segments.extend({"text":t["text"],"start":new["start"]+t["start"],"end":new["start"]+t["end"]} for t in ts)
    (folder/"captions.srt").write_text(subtitles(segments),encoding="utf-8")
    normalise_audio(folder,c,offset,progress)
    (clips/"concat.txt").write_text("".join(f"file '{s['id']:03}.mp4'\n" for s in project["scenes"]),encoding="utf-8")
    dest=folder/("preview.mp4" if preview else "final.mp4");temp=dest.with_name(dest.stem+".partial.mp4")
    args=["ffmpeg","-y","-v","error","-filter_threads","1","-f","concat","-safe","1","-i",clips/"concat.txt","-i",folder/"master.wav","-map","0:v:0","-map","1:a:0"]
    if c["burn_captions"]:
        # Working directory keeps Windows drive colons out of the FFmpeg filter.
        args += ["-vf","subtitles=filename=captions.srt:force_style='FontSize=22,Outline=2,MarginV=45'","-c:v","libx264","-threads","2","-crf",c["crf"],"-preset",c["preset"]]
    else:args += ["-c:v","copy"]
    args += ["-c:a","aac","-b:a","192k","-ar","48000","-t",f"{offset:.6f}","-movflags","+faststart",temp]
    progress("Assembling the video master…");run(args,cwd=folder);temp.replace(dest)
    info=probe(dest);video=next(s for s in info["streams"] if s.get("codec_type")=="video");audio=next(s for s in info["streams"] if s.get("codec_type")=="audio")
    actual=float(info["format"]["duration"])
    if abs(actual-offset)>.2 or video["width"]!=width or video["height"]!=height:raise ValueError("Export failed duration or dimension checks")
    progress("Decoding the complete export and measuring its delivered audio…")
    decoded=run(["ffmpeg","-hide_banner","-xerror","-i",dest,"-af","loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json","-f","null","-"],1800)
    measurements=re.findall(r"\{[^{}]*\}",decoded.stderr,re.S)
    if not measurements:raise ValueError("Export audio measurement is unavailable")
    delivered=json.loads(measurements[-1])
    integrated=float(delivered["input_i"]);peak=float(delivered["input_tp"])
    if not math.isfinite(integrated) or not math.isfinite(peak) or peak>=0:raise ValueError("Delivered audio is silent, invalid or has no true-peak headroom")
    if abs(integrated+16)>2:warnings.append("Delivered integrated loudness differs from the −16 LUFS target by over 2 LU; review the mix.")
    if peak>-1:warnings.append("Delivered audio has less than 1 dB true-peak headroom; review before publication.")
    quality={"technical_pass":True,"preview":preview,"duration":actual,"width":width,"height":height,"codec":video["codec_name"],"audio_codec":audio["codec_name"],"delivered_lufs":integrated,"delivered_true_peak_dbtp":peak,"warnings":warnings,"video_sha256":file_signature(dest),"note":"Technical checks do not approve story, art continuity, factual/rights claims or platform eligibility."}
    save(folder/("preview-quality.json" if preview else "quality.json"),quality)
    return dest


def contact_sheet(folder, project):
    tilew,tileh=384,216;cols=3;rows=math.ceil(len(project["scenes"])/cols)
    sheet=Image.new("RGB",(cols*tilew,rows*(tileh+52)),"#111b2a");draw=ImageDraw.Draw(sheet)
    for i,s in enumerate(project["scenes"]):
        path=folder/"art"/f"{s['id']:03}.png";x=(i%cols)*tilew;y=(i//cols)*(tileh+52)
        if path.exists():
            with Image.open(path) as image:sheet.paste(ImageOps.fit(image.convert("RGB"),(tilew,tileh)),(x,y))
        draw.text((x+10,y+tileh+7),f"{s['id']:02} / {s['beat']}",fill="#c4efa0")
        draw.text((x+10,y+tileh+26),s["narration"][:52],fill="white")
    sheet.save(folder/"contact-sheet.jpg",quality=90)
    # A clean art-based thumbnail candidate; no promise that it maximises CTR.
    cover=folder/"art"/f"{project['scenes'][0]['id']:03}.png"
    if cover.exists():
        with Image.open(cover) as im:ImageOps.fit(im.convert("RGB"),(1280,720)).save(folder/"thumbnail.jpg",quality=94)
