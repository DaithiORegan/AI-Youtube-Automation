import json
import os
import re
import time
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
PLAN = BASE / "output" / "scene_plan.json"
READY = BASE / "output" / "scene_plan_ready.json"
FOOTAGE = BASE / "assets" / "footage"
CACHE = BASE / "assets" / "pixabay_cache.json"
SOURCES = BASE / "assets" / "footage_sources.json"

# QUALITY RULES
MIN_WIDTH = 1920
MIN_HEIGHT = 1080
PREFERRED_ORDER = ["large", "medium", "small", "tiny"]
MAX_DOWNLOAD_MB = 700
SEARCH_LIMIT = 6
RESULTS_PER_QUERY = 30
CACHE_SECONDS = 86400

load_dotenv(BASE / ".env")
API_KEY = os.getenv("PIXABAY_API_KEY")

if not API_KEY:
    raise RuntimeError("Missing PIXABAY_API_KEY in .env")

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


def ffprobe_resolution(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    text = result.stdout.strip()
    if not text:
        return 0, 0

    width, height = text.split(",")
    return int(width), int(height)


def is_resolution_good(width, height):
    return width >= MIN_WIDTH and height >= MIN_HEIGHT


def normalise_query_words(text):
    words = re.findall(r"[a-z0-9]+", text.lower())

    stopwords = {
        "a", "an", "the", "of", "in", "on", "for", "with", "and",
        "to", "from", "showing", "footage", "video", "shot", "scene",
        "cinematic", "suitable", "visual", "clip", "clips", "documentary"
    }

    cleaned = [w for w in words if w not in stopwords]
    return cleaned[:5]


def scene_query_words(scene):
    seed_text = scene.get("visual_search") or scene.get("narration") or ""
    words = normalise_query_words(seed_text)

    if not words:
        words = normalise_query_words(scene.get("narration", ""))

    return words[:4]


def pixabay_api(params):
    response = session.get(
        "https://pixabay.com/api/videos/",
        params={
            "key": API_KEY,
            **params
        },
        timeout=60
    )
    response.raise_for_status()
    return response.json()


def search_pixabay(query_words, cache):
    query = " ".join(query_words)
    now = time.time()

    cached = cache.get(query)
    if cached and now - cached["timestamp"] < CACHE_SECONDS:
        return cached["hits"]

    data = pixabay_api({
        "q": query,
        "per_page": RESULTS_PER_QUERY,
        "safesearch": "true"
    })

    hits = data.get("hits", [])

    cache[query] = {
        "timestamp": now,
        "hits": hits
    }
    save_json(CACHE, cache)

    return hits


def fetch_by_id(video_id):
    data = pixabay_api({"id": str(video_id)})
    hits = data.get("hits", [])

    if not hits:
        raise RuntimeError(f"Pixabay video {video_id} not found")

    return hits[0]


def choose_variant(hit):
    versions = hit.get("videos", {})

    for variant_name in PREFERRED_ORDER:
        variant = versions.get(variant_name, {})
        width = int(variant.get("width") or 0)
        height = int(variant.get("height") or 0)
        url = variant.get("url")

        if url and is_resolution_good(width, height):
            return variant_name, variant

    return None, None


def score_hit(hit, query_words):
    tags = set(re.findall(r"[a-z0-9]+", hit.get("tags", "").lower()))
    overlap = len(tags.intersection(set(query_words)))

    variant_name, variant = choose_variant(hit)
    if not variant:
        return -1

    width = int(variant.get("width") or 0)
    height = int(variant.get("height") or 0)

    resolution_score = (width * height) / (1920 * 1080)
    duration = int(hit.get("duration") or 0)

    duration_score = 0
    if 6 <= duration <= 30:
        duration_score = 1.5
    elif 4 <= duration <= 45:
        duration_score = 1.0

    return overlap * 10 + resolution_score + duration_score


def download_variant(hit, sources):
    video_id = str(hit["id"])
    filename = f"pixabay_{video_id}.mp4"
    destination = FOOTAGE / filename

    variant_name, variant = choose_variant(hit)
    if not variant:
        raise RuntimeError(f"No acceptable 1080p+ variant for video {video_id}")

    expected_width = int(variant["width"])
    expected_height = int(variant["height"])
    url = variant["url"]

    # Reuse only if the existing local file is already good enough
    if destination.exists() and destination.stat().st_size > 0:
        try:
            actual_width, actual_height = ffprobe_resolution(destination)

            if is_resolution_good(actual_width, actual_height):
                print(f"  Reusing HD file: {filename} ({actual_width}x{actual_height})")

                sources[filename] = {
                    "provider": "Pixabay",
                    "id": hit["id"],
                    "page_url": hit.get("pageURL", ""),
                    "creator": hit.get("user", ""),
                    "tags": hit.get("tags", ""),
                    "license": "Pixabay Content License",
                    "variant": variant_name,
                    "width": actual_width,
                    "height": actual_height,
                    "size_bytes": destination.stat().st_size
                }
                save_json(SOURCES, sources)
                return filename
            else:
                print(f"  Existing file too small, replacing: {filename} ({actual_width}x{actual_height})")
        except Exception:
            print(f"  Could not inspect existing file, replacing: {filename}")

    print(f"  Downloading {filename} at {expected_width}x{expected_height} ({variant_name})")

    temp_path = destination.with_suffix(".part")
    max_bytes = MAX_DOWNLOAD_MB * 1024 * 1024

    try:
        with session.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()

            downloaded = 0
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue

                    downloaded += len(chunk)

                    if downloaded > max_bytes:
                        raise RuntimeError("Download exceeded size limit")

                    handle.write(chunk)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            raise RuntimeError("Downloaded file is empty")

        actual_width, actual_height = ffprobe_resolution(temp_path)

        if not is_resolution_good(actual_width, actual_height):
            raise RuntimeError(
                f"Downloaded clip rejected: {actual_width}x{actual_height} is below 1920x1080"
            )

        temp_path.replace(destination)

        sources[filename] = {
            "provider": "Pixabay",
            "id": hit["id"],
            "page_url": hit.get("pageURL", ""),
            "creator": hit.get("user", ""),
            "tags": hit.get("tags", ""),
            "license": "Pixabay Content License",
            "variant": variant_name,
            "width": actual_width,
            "height": actual_height,
            "size_bytes": destination.stat().st_size
        }
        save_json(SOURCES, sources)

        return filename

    finally:
        if temp_path.exists():
            temp_path.unlink()


def clear_low_quality_scene_links(scenes, sources):
    """
    If a scene points to a local Pixabay clip that is below 1080p,
    clear the scene assignment so a replacement can be searched.
    """
    for scene in scenes:
        filename = scene.get("filename")
        if not filename:
            continue

        clip_path = FOOTAGE / filename
        if not clip_path.exists():
            scene["filename"] = None
            scene["footage_status"] = "missing_local_file"
            continue

        try:
            width, height = ffprobe_resolution(clip_path)

            if not is_resolution_good(width, height):
                print(
                    f"Scene {scene['scene']}: rejecting low-quality clip "
                    f"{filename} ({width}x{height})"
                )
                scene["filename"] = None
                scene["source_id"] = None
                scene["source_url"] = ""
                scene["footage_status"] = "rejected_low_quality"
        except Exception as error:
            print(f"Scene {scene['scene']}: could not inspect {filename}: {error}")
            scene["filename"] = None
            scene["source_id"] = None
            scene["source_url"] = ""
            scene["footage_status"] = "inspection_failed"


def upgrade_existing_pixabay_sources(sources):
    """
    Re-check existing Pixabay downloads already recorded in footage_sources.json.
    If a higher acceptable variant exists, re-download it.
    """
    ids = []

    for filename, meta in sources.items():
        provider = meta.get("provider")
        video_id = meta.get("id")

        if provider == "Pixabay" and video_id:
            ids.append(int(video_id))

    ids = sorted(set(ids))
    print(f"Checking {len(ids)} previously recorded Pixabay clips for HD quality...")

    for video_id in ids:
        try:
            hit = fetch_by_id(video_id)
            download_variant(hit, sources)
        except Exception as error:
            print(f"  Could not upgrade Pixabay ID {video_id}: {error}")


def find_best_hit(query_words, cache, rejected_ids):
    hits = search_pixabay(query_words, cache)

    ranked = sorted(
        hits,
        key=lambda item: score_hit(item, query_words),
        reverse=True
    )

    for hit in ranked:
        hit_id = int(hit["id"])

        if hit_id in rejected_ids:
            continue

        if score_hit(hit, query_words) < 10:
            continue

        variant_name, variant = choose_variant(hit)
        if not variant:
            continue

        return hit

    return None


def main():
    original_plan = load_json(PLAN, [])
    previous_ready = load_json(READY, [])
    sources = load_json(SOURCES, {})
    cache = load_json(CACHE, {})

    if not original_plan and not previous_ready:
        raise RuntimeError("No scene plan available")

    # Use original plan if available, otherwise fallback to previous ready plan
    scenes = original_plan if original_plan else previous_ready

    # Carry forward old assignments
    previous_by_scene = {item["scene"]: item for item in previous_ready}

    for scene in scenes:
        previous = previous_by_scene.get(scene["scene"], {})

        if not scene.get("filename"):
            scene["filename"] = previous.get("filename")

        if not scene.get("source_id"):
            scene["source_id"] = previous.get("source_id")

        if not scene.get("source_url"):
            scene["source_url"] = previous.get("source_url", "")

    # First, try to upgrade any previously downloaded Pixabay clips
    upgrade_existing_pixabay_sources(sources)

    # Then reject any scenes still linked to sub-1080p local files
    clear_low_quality_scene_links(scenes, sources)

    rejected_ids = set()
    searches_used = 0

    unresolved = [scene for scene in scenes if not scene.get("filename")]
    print(f"Scenes needing Full HD footage: {len(unresolved)}")

    for scene in scenes:
        if scene.get("filename"):
            continue

        if searches_used >= SEARCH_LIMIT:
            print("Search limit reached.")
            break

        query_words = scene_query_words(scene)
        if not query_words:
            scene["footage_status"] = "no_query_terms"
            continue

        searches_used += 1
        print(f"\nScene {scene['scene']}: searching for {' '.join(query_words)}")

        try:
            selected = find_best_hit(query_words, cache, rejected_ids)

            if not selected:
                scene["footage_status"] = "needs_review"
                print("  No acceptable 1080p+ Pixabay result found.")
                save_json(READY, scenes)
                continue

            filename = download_variant(selected, sources)

            # Final safety check against the actual saved file
            final_width, final_height = ffprobe_resolution(FOOTAGE / filename)
            if not is_resolution_good(final_width, final_height):
                raise RuntimeError(
                    f"Downloaded file failed final quality check: {final_width}x{final_height}"
                )

            scene["filename"] = filename
            scene["source_id"] = selected["id"]
            scene["source_url"] = selected.get("pageURL", "")
            scene["footage_status"] = "downloaded"

            print(f"  Selected: {filename} ({final_width}x{final_height})")

        except Exception as error:
            scene["filename"] = None
            scene["source_id"] = None
            scene["source_url"] = ""
            scene["footage_status"] = "failed"
            print(f"  Error: {error}")

        save_json(READY, scenes)

    save_json(READY, scenes)

    print("\nFULL HD FOOTAGE ENFORCEMENT COMPLETE")
    print(f"Updated scene plan: {READY}")
    print(f"Source records: {SOURCES}")


if __name__ == "__main__":
    main()