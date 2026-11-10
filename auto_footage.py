
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
PLAN = BASE / "output" / "scene_plan.json"
UPDATED = BASE / "output" / "scene_plan_ready.json"
FOOTAGE = BASE / "assets" / "footage"
CACHE = BASE / "assets" / "pixabay_cache.json"
SOURCES = BASE / "assets" / "footage_sources.json"

load_dotenv(BASE / ".env")
API_KEY = os.getenv("PIXABAY_API_KEY")

if not API_KEY:
    raise RuntimeError("PIXABAY_API_KEY is missing.")

FOOTAGE.mkdir(parents=True, exist_ok=True)

session = requests.Session()

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def make_query(scene):
    text = scene.get("visual_search") or scene["narration"]
    text = re.sub(r"[^a-zA-Z0-9 ]", " ", text)
    words = text.lower().split()

    stopwords = {
        "a", "an", "the", "of", "in", "on", "for",
        "with", "and", "to", "from", "showing",
        "footage", "video", "shot", "scene",
        "cinematic", "suitable", "visual"
    }

    filtered = [w for w in words if w not in stopwords]

    # Short searches are more effective for stock footage.
    return " ".join(filtered[:3])[:100]

def search_pixabay(query, cache):
    now = time.time()
    entry = cache.get(query)

    # Reuse API responses for at least 24 hours.
    if entry and now - entry["timestamp"] < 86400:
        print(f"  Using cached search: {query}")
        return entry["hits"]

    response = session.get(
        "https://pixabay.com/api/videos/",
        params={
            "key": API_KEY,
            "q": query,
            "per_page": 10,
            "safesearch": "true"
        },
        timeout=40
    )
    response.raise_for_status()

    hits = response.json().get("hits", [])

    cache[query] = {
        "timestamp": now,
        "hits": hits
    }
    save_json(CACHE, cache)

    return hits

def rank_results(hits, query):
    terms = set(query.lower().split())

    def score(hit):
        tags = set(
            re.findall(
                r"[a-z0-9]+",
                hit.get("tags", "").lower()
            )
        )
        matches = len(terms & tags)

        width = hit.get("videos", {}).get(
            "medium", {}
        ).get("width", 0)

        return matches * 10 + (2 if width >= 1280 else 0)

    return sorted(hits, key=score, reverse=True)

def download_video(hit):
    video_id = str(hit["id"])
    filename = f"pixabay_{video_id}.mp4"
    destination = FOOTAGE / filename

    if destination.exists() and destination.stat().st_size > 0:
        print(f"  Reusing existing file: {filename}")
        return filename

    versions = hit.get("videos", {})

    # Prefer medium quality to minimise download size.
    variant = versions.get("medium", {})
    url = variant.get("url")

    if not url:
        raise RuntimeError("No usable video URL returned.")

    print(f"  Downloading Pixabay video {video_id}...")

    temp_path = destination.with_suffix(".part")

    try:
        with session.get(url, stream=True, timeout=90) as response:
            response.raise_for_status()

            downloaded = 0
            max_bytes = 150 * 1024 * 1024

            with temp_path.open("wb") as file:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue

                    downloaded += len(chunk)

                    if downloaded > max_bytes:
                        raise RuntimeError("Download exceeds 150 MB.")

                    file.write(chunk)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            raise RuntimeError("Downloaded file is empty.")

        temp_path.replace(destination)

    finally:
        if temp_path.exists():
            temp_path.unlink()

    return filename

def main():
    if not PLAN.exists():
        raise FileNotFoundError(PLAN)

    scenes = load_json(PLAN, [])
    cache = load_json(CACHE, {})
    sources = load_json(SOURCES, {})

    missing = [
        s for s in scenes
        if not s.get("filename")
    ]

    print(f"Found {len(missing)} scenes needing footage.")

    # Small controlled test, not a mass-download crawler.
    maximum_searches = 3
    searches = 0

    for scene in scenes:
        if scene.get("filename"):
            continue

        if searches >= maximum_searches:
            print("Search limit reached.")
            break

        query = make_query(scene)

        if not query:
            print(f"Scene {scene['scene']}: No search terms.")
            continue

        print(f"\nScene {scene['scene']}: {query}")
        searches += 1

        try:
            hits = search_pixabay(query, cache)

            if not hits:
                print("  No matching results.")
                scene["footage_status"] = "not_found"
                continue

            ranked = rank_results(hits, query)
            best = ranked[0]

            # Require at least one matching tag.
            tags = set(
                re.findall(
                    r"[a-z0-9]+",
                    best.get("tags", "").lower()
                )
            )

            if not set(query.split()) & tags:
                print("  No sufficiently relevant tags.")
                scene["footage_status"] = "needs_review"
                continue

            filename = download_video(best)

            scene["filename"] = filename
            scene["footage_status"] = "downloaded"
            scene["source_id"] = best["id"]
            scene["source_url"] = best.get("pageURL", "")

            sources[filename] = {
                "provider": "Pixabay",
                "id": best["id"],
                "page_url": best.get("pageURL", ""),
                "creator": best.get("user", ""),
                "tags": best.get("tags", ""),
                "duration": best.get("duration", 0),
                "license": "Pixabay Content License"
            }

            save_json(SOURCES, sources)
            save_json(UPDATED, scenes)

            print(f"  Selected: {filename}")
            print(f"  Tags: {best.get('tags', '')}")

        except Exception as error:
            scene["footage_status"] = "failed"
            print(f"  Failed: {type(error).__name__}: {error}")

        save_json(UPDATED, scenes)

    print("\nFOOTAGE ACQUISITION FINISHED")
    print(f"Updated scene plan: {UPDATED}")

if __name__ == "__main__":
    main()
