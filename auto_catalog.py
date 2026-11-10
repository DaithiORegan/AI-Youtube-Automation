
import base64
import json
import subprocess
import tempfile
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
FOOTAGE = BASE / "assets" / "footage"
CATALOG = BASE / "assets" / "footage_catalog.json"

MODEL = "gemma3:4b"
API = "http://localhost:11434/api/generate"


def duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return float(result.stdout.strip())


def extract_frame(video, seconds, destination):
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(seconds),
            "-i", str(video),
            "-frames:v", "1",
            "-vf", "scale=640:-2",
            str(destination)
        ],
        check=True
    )


def analyse_frame(image_path):
    encoded = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    response = requests.post(
        API,
        json={
            "model": MODEL,
            "prompt": (
                "Describe exactly what is visually shown in "
                "this video frame. Do not invent context. "
                "Return JSON with two fields: "
                "'description' (one concise sentence) and "
                "'keywords' (an array of 5 short visual tags)."
            ),
            "images": [encoded],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1}
        },
        timeout=600
    )
    response.raise_for_status()

    data = json.loads(response.json()["response"])
    return data


def main():
    FOOTAGE.mkdir(parents=True, exist_ok=True)

    existing = {}
    if CATALOG.exists():
        for item in json.loads(
            CATALOG.read_text(encoding="utf-8")
        ):
            existing[item["filename"]] = item

    videos = sorted(FOOTAGE.glob("*.mp4"))
    results = []

    print(f"Found {len(videos)} videos.")

    for i, video in enumerate(videos, 1):
        previous = existing.get(video.name)

        if previous and previous.get("description"):
            print(f"[{i}/{len(videos)}] Cached: {video.name}")
            results.append(previous)
            continue

        print(f"[{i}/{len(videos)}] Analysing: {video.name}")

        try:
            length = duration(video)

            with tempfile.TemporaryDirectory() as temp:
                image_path = Path(temp) / "frame.jpg"

                # Sample the middle of each clip.
                extract_frame(
                    video,
                    max(0, length / 2),
                    image_path
                )

                analysis = analyse_frame(image_path)

            item = {
                "filename": video.name,
                "duration": round(length, 2),
                "description": analysis["description"],
                "keywords": analysis["keywords"]
            }

            print("  ", item["description"])
            results.append(item)

            # Save progress after each clip.
            CATALOG.write_text(
                json.dumps(results, indent=2),
                encoding="utf-8"
            )

        except Exception as error:
            print(f"  FAILED: {error}")

    CATALOG.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8"
    )

    print(f"\nCatalogued {len(results)} videos.")
    print(f"Saved to: {CATALOG}")


if __name__ == "__main__":
    main()
