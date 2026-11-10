
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
FOOTAGE = BASE / "assets" / "footage"
CATALOG = BASE / "assets" / "footage_catalog.json"

def get_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return round(
        float(json.loads(result.stdout)["format"]["duration"]),
        2
    )

existing = {}

if CATALOG.exists():
    for item in json.loads(CATALOG.read_text(encoding="utf-8")):
        existing[item["filename"]] = item

catalog = []

for clip in sorted(FOOTAGE.glob("*.mp4")):
    previous = existing.get(clip.name, {})

    catalog.append({
        "filename": clip.name,
        "duration": get_duration(clip),
        "description": previous.get("description", ""),
        "keywords": previous.get("keywords", [])
    })

CATALOG.write_text(
    json.dumps(catalog, indent=2),
    encoding="utf-8"
)

print(f"Catalogued {len(catalog)} videos.")
print(f"Saved to: {CATALOG}")
