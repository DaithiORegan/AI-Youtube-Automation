
import json
import re
from pathlib import Path
import requests

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
CATALOG = BASE / "assets" / "footage_catalog.json"
TIMESTAMPS = OUTPUT / "timestamps.json"
PLAN = OUTPUT / "scene_plan.json"

MODEL = "qwen3:4b"
SCENE_SECONDS = 5.0

# Load available footage and narration timings.
catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
words = json.loads(TIMESTAMPS.read_text(encoding="utf-8"))

if not catalog:
    raise RuntimeError("Footage catalogue is empty.")

if not words:
    raise RuntimeError("No narration timestamps found.")

# Divide the narration into approximately five-second scenes.
scenes = []
group = []
start = float(words[0]["start"])

for word in words:
    if group and float(word["end"]) - start > SCENE_SECONDS:
        scenes.append(group)
        group = []
        start = float(word["start"])
    group.append(word)

if group:
    scenes.append(group)

available = [
    {
        "filename": item["filename"],
        "description": item["description"],
        "keywords": item["keywords"]
    }
    for item in catalog
    if item.get("description")
]

results = []

for index, scene in enumerate(scenes, 1):
    narration = " ".join(w["word"] for w in scene)
    start_time = float(scene[0]["start"])
    end_time = float(scene[-1]["end"])

    prompt = f"""
You are a professional documentary video editor.

Choose the most relevant footage for this narration.

NARRATION:
{narration}

AVAILABLE FOOTAGE:
{json.dumps(available, ensure_ascii=False)}

RULES:
- Use ONLY an exact filename from the catalogue.
- Base your choice on what is visually depicted.
- Do not invent footage or filenames.
- If nothing is visually relevant, return null for filename.
- Avoid choosing footage merely because it looks cinematic.
- Return JSON only.

Required JSON:
{{
  "filename": null,
  "reason": "Short explanation of the decision",
  "visual_search": "A suitable visual to source if needed"
}}
"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 350
            }
        },
        timeout=600
    )
    response.raise_for_status()

    try:
        choice = json.loads(response.json()["response"])
    except (ValueError, KeyError):
        choice = {}

    filename = choice.get("filename")
    valid_names = {item["filename"] for item in available}

    if filename not in valid_names:
        filename = None

    item = {
        "scene": index,
        "start": round(start_time, 2),
        "end": round(end_time, 2),
        "narration": narration,
        "filename": filename,
        "reason": choice.get("reason", ""),
        "visual_search": choice.get("visual_search", "")
    }

    results.append(item)

    # Save progress after every scene.
    PLAN.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(
        f"Scene {index}/{len(scenes)}: "
        f"{filename or 'NEEDS FOOTAGE'}",
        flush=True
    )

print("\nAI SCENE PLAN GENERATED!")
print(f"Saved to: {PLAN}")
