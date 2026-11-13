"""Tiny synthetic renderer test, deliberately not a publishable video."""
from pathlib import Path
import numpy as np
import soundfile as sf
from PIL import Image,ImageDraw
from .core import DEFAULTS,STYLE,save


def demo(folder,progress=print):
    if (folder/"project.json").exists():raise ValueError("Demo folder already exists; choose another folder to preserve prior work")
    folder.mkdir(parents=True,exist_ok=True);(folder/"art").mkdir();(folder/"audio").mkdir()
    scenes=[]
    for i,(beat,colour,camera) in enumerate([("hook","#24394b","push"),("reversal","#4b3846","left"),("payoff","#284741","pull")],1):
        image=Image.new("RGB",(1280,720),colour);draw=ImageDraw.Draw(image)
        draw.ellipse((800-i*90,70,1200-i*90,470),fill="#c4e5a4");draw.rectangle((0,500,1280,720),fill="#101924")
        draw.rounded_rectangle((220+i*40,280,370+i*40,570),radius=60,fill="#d6a868");draw.ellipse((230+i*40,200,360+i*40,330),fill="#f0dcc0")
        draw.text((50,55),f"STORYFORGE / SYNTHETIC TECHNICAL TEST / SHOT {i}",fill="white")
        image.save(folder/"art"/f"{i:03}.png")
        sr=24000;t=np.arange(round(sr*2.2))/sr
        audio=(.12*np.sin(2*np.pi*(210+i*35)*t)*(.5+.5*np.sin(2*np.pi*3*t))).astype(np.float32)
        audio[:240]*=np.linspace(0,1,240);audio[-240:]*=np.linspace(1,0,240)
        sf.write(folder/"audio"/f"{i:03}.wav",audio,sr)
        scenes.append({"id":i,"beat":beat,"narration":"Technical test tone only. This is not a spoken story.","image_prompt":"Procedural coloured geometry for renderer verification, not finished art.","camera":camera,"art_source":"manual"})
    p={"schema_version":1,"technical_demo":True,"fiction":True,"title":"Technical renderer test — not for publication","premise":"Verify the export pipeline without downloading AI models.","character_bible":"Procedural test figure; no generated likeness.","style_bible":STYLE,"settings":DEFAULTS,"scenes":scenes}
    save(folder/"project.json",p)
    from .production import pipeline
    pipeline(folder/"project.json",("render","package"),preview=True,progress=progress)
    progress("This is a technical preview with tones and procedural images, not a quality demonstration or publishable film.")
