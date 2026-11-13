import json
import math
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .core import DEFAULTS, STYLE, config, load, save, scene_prompt, signature, validate


def local_session(url):
    p=urlsplit(url)
    if p.scheme!="http" or p.hostname not in ("127.0.0.1","localhost","::1") or p.username or p.password or p.path.strip("/") or p.query or p.fragment:
        raise ValueError("AI services must use a local HTTP origin; no paid or remote provider is used")
    session=requests.Session();session.trust_env=False
    return session


def ollama(c, prompt, schema=True):
    session=local_session(c["ollama_url"])
    payload={"model":c["model"],"prompt":prompt,"stream":False,"think":False,"keep_alive":0,"options":{"temperature":.65,"num_predict":10000,"num_ctx":16384,"seed":c["seed"]}}
    if schema:payload["format"]="json"
    try:
        r=session.post(c["ollama_url"]+"/api/generate",json=payload,timeout=(5,900));r.raise_for_status()
        value=r.json().get("response","").strip()
        if not value:raise ValueError("Ollama returned an empty response")
        return json.loads(value) if schema else value
    except requests.RequestException as exc:
        raise RuntimeError("Ollama is unavailable. Start Ollama and pull the configured model; run storyforge doctor.") from exc


def create(topic, seconds, settings=None, progress=print):
    if not 30<=seconds<=360:raise ValueError("Start with 30–360 seconds; default pilot is 90 seconds")
    c={**DEFAULTS,**(settings or {})};count=max(5,math.ceil(seconds/9))
    # A previous interrupted illustration session may still occupy VRAM.
    # This only unloads ComfyUI models; it does not cancel its queued work.
    try:local_session(c["comfy_url"]).post(c["comfy_url"]+"/free",json={"unload_models":True,"free_memory":True},timeout=5)
    except requests.RequestException:pass
    prompt=f"""Write an ORIGINAL fictional short film, not a documentary. Premise requested: {topic}
Target {seconds} seconds, approximately {round(seconds*2.25)} spoken words across {count} distinct visual scenes.
Create a distinctive protagonist, desire, obstacle, escalating consequences, a causal reversal and an earned final payoff. Reveal the premise in the first two sentences through an event, not an explanation. Each scene must advance the plot. Vary shot size and setting. No generic filler, repeated exposition, copied characters, channel branding, celebrity likeness or requests to like and subscribe. Never claim fictional events are real. Avoid graphic violence and sexual content.
The visuals will be still illustrations with camera motion, not full character animation: choose legible single actions, facial reactions and changes of scene. No crowds of identical protagonists. Do not rely on generated words, UI text or tiny numbers to explain the story.
Return JSON ONLY with title (specific and honest), premise, character_bible (original named protagonist with precise immutable costume/face/colours), style_bible, description (identify it as original illustrated fiction), scenes array. Each scene has id (consecutive integer), beat (hook/setup/escalation/reversal/payoff), narration (spoken prose only, 12–35 words), image_prompt (one precise illustrated shot, subject, action, emotion, environment, lighting, composition), camera (push/pull/left/right). First beat is hook, final is payoff; include at least one reversal. Style baseline: {STYLE}
Do not include settings, commentary or internal reasoning."""
    progress("Writing original story and shot plan with local Ollama…")
    p=ollama(c,prompt)
    progress("Running an editorial revision for causality, payoff, continuity and repetition…")
    revised=ollama(c,"Act as a demanding fiction editor. Revise this project once. Preserve its JSON structure. Fix weak cause-and-effect, inconsistent character descriptions, repetitive narration and an unearned ending. Keep the first scene a hook, include a reversal and make the final scene a payoff. Target "+str(round(seconds*2.25))+" spoken words, 3–65 words per scene. Return the COMPLETE corrected JSON project only, without settings.\n"+json.dumps(p,ensure_ascii=False))
    p=validate(revised)
    word_count=sum(len(s["narration"].split()) for s in p["scenes"])
    if not seconds*1.5<=word_count<=seconds*3.1:
        raise ValueError(f"Writer missed the duration brief ({word_count} words). Try a shorter/simpler topic; no poor-length project was accepted.")
    p["settings"]=c;p["schema_version"]=1;p["target_seconds"]=seconds;p["fiction"]=True
    return p


def workflow(c, prompt, seed):
    return {
      "1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":c["checkpoint"]}},
      "2":{"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["1",1]}},
      "3":{"class_type":"CLIPTextEncode","inputs":{"text":"letters, captions, text, watermark, logo, low resolution, blurry, distorted hands, extra limbs, duplicate protagonist, photographic celebrity, inconsistent costume","clip":["1",1]}},
      "4":{"class_type":"EmptyLatentImage","inputs":{"width":c["image_width"],"height":c["image_height"],"batch_size":1}},
      "5":{"class_type":"KSampler","inputs":{"seed":seed,"steps":c["steps"],"cfg":6.5,"sampler_name":"dpmpp_2m","scheduler":"karras","denoise":1.0,"model":["1",0],"positive":["2",0],"negative":["3",0],"latent_image":["4",0]}},
      "6":{"class_type":"VAEDecode","inputs":{"samples":["5",0],"vae":["1",2]}},
      "7":{"class_type":"SaveImage","inputs":{"filename_prefix":"storyforge/scene","images":["6",0]}}
    }


def images(folder, project, progress=print):
    c=config(project);session=local_session(c["comfy_url"]);cache_path=folder/"image-cache.json"
    cache=load(cache_path) if cache_path.exists() else {}
    client=uuid.uuid4().hex
    for s in project["scenes"]:
        dest=folder/"art"/f"{s['id']:03}.png";key=str(s["id"])
        if s.get("art_source")=="manual":
            if not dest.is_file():raise ValueError(f"Scene {key} is set to manual art but {dest} is missing")
            progress(f"Art {key}: manual illustration preserved");continue
        graph=workflow(c,scene_prompt(project,s),c["seed"]+s["id"])
        expected=signature(graph)
        if dest.is_file() and cache.get(key,{}).get("signature")==expected:
            progress(f"Art {key}: unchanged; reused");continue
        progress(f"Painting scene {key}/{len(project['scenes'])} locally…")
        try:
            r=session.post(c["comfy_url"]+"/prompt",json={"prompt":graph,"client_id":client},timeout=15);r.raise_for_status();reply=r.json()
            if reply.get("node_errors"):raise ValueError("ComfyUI rejected workflow nodes: "+str(reply["node_errors"])[:500])
            job=reply["prompt_id"];started=time.monotonic()
            while time.monotonic()-started<900:
                r=session.get(c["comfy_url"]+"/history/"+job,timeout=10);r.raise_for_status();item=r.json().get(job)
                if item:
                    status=item.get("status",{})
                    if status.get("status_str")=="error":raise RuntimeError("ComfyUI generation failed; inspect its local console (often checkpoint/VRAM).")
                    output=item.get("outputs",{}).get("7",{}).get("images",[])
                    if output:
                        image=output[0]
                        r=session.get(c["comfy_url"]+"/view",params={"filename":image["filename"],"subfolder":image.get("subfolder",""),"type":image.get("type","output")},timeout=90);r.raise_for_status()
                        if len(r.content)>40*1024*1024:raise ValueError("Generated image exceeds 40 MiB")
                        from PIL import Image
                        import io
                        data=Image.open(io.BytesIO(r.content));data.load()
                        dest.parent.mkdir(parents=True,exist_ok=True);data.convert("RGB").save(dest)
                        cache[key]={"signature":expected,"checkpoint":c["checkpoint"],"seed":c["seed"]+s["id"],"method":"local ComfyUI SDXL"};save(cache_path,cache)
                        break
                    if status.get("completed"):raise RuntimeError("ComfyUI completed without an image")
                time.sleep(1)
            else:raise TimeoutError("Scene exceeded 15 minutes; job may still be running in ComfyUI. Check its queue before resuming.")
        except requests.RequestException as exc:
            raise RuntimeError("ComfyUI is unavailable or rejected the render. Start it on port 8188 and install the configured SDXL checkpoint.") from exc
    # Release diffusion weights before a later Ollama request on an 8 GB GPU.
    try:session.post(c["comfy_url"]+"/free",json={"unload_models":True,"free_memory":True},timeout=10)
    except requests.RequestException:pass
