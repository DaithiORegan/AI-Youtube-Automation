
import json
import subprocess
import sys
import time
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)

INPUT = BASE / "input" / "narration.wav"
OUTPUT = BASE / "output"
ASSETS = BASE / "assets"

TIMESTAMPS = OUTPUT / "timestamps.json"
CAPTIONS = OUTPUT / "captions.ass"
SCENE_PLAN = OUTPUT / "scene_plan.json"
READY_PLAN = OUTPUT / "scene_plan_ready.json"
FINAL_VIDEO = OUTPUT / "ai_documentary.mp4"

SCRIPTS = [
    "transcribe.py",
    "captions_generator.py",
    "scene_planner.py",
    "auto_footage.py",
    "ai_video_renderer.py"
]


def check_file(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Required file not found: {path}"
        )


def run_script(filename):
    print(f"\n{'=' * 50}")
    print(f"RUNNING: {filename}")
    print(f"{'=' * 50}", flush=True)

    start = time.time()

    subprocess.run(
        [str(PYTHON), str(BASE / filename)],
        cwd=BASE,
        check=True
    )

    elapsed = time.time() - start
    print(
        f"Completed {filename} in {elapsed:.1f}s",
        flush=True
    )


def main():
    started = time.time()

    OUTPUT.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("       YOUTUBE AI PRODUCTION SYSTEM")
    print("=" * 55)
    print("Mode: Fully automated local production")
    print("Narration: Your recorded voice")
    print("Captions: Animated word highlighting")
    print("Footage: AI selected")
    print("Music: Automatic background mixing")

    # Validate required input files
    check_file(INPUT)
    check_file(ASSETS / "music" / "background.mp3")
    check_file(ASSETS / "footage_catalog.json")
    check_file(PYTHON)

    # Validate all pipeline scripts
    for filename in SCRIPTS:
        check_file(BASE / filename)

    # Step 1: Transcribe narration
    run_script("transcribe.py")
    check_file(TIMESTAMPS)

    # Step 2: Generate animated captions
    run_script("captions_generator.py")
    check_file(CAPTIONS)

    # Step 3: Generate AI editing decisions
    run_script("scene_planner.py")
    check_file(SCENE_PLAN)

    # Step 4: Find and download missing footage
    run_script("auto_footage.py")
    check_file(READY_PLAN)

    # Step 5: Render video with music and captions
    run_script("ai_video_renderer.py")
    check_file(FINAL_VIDEO)

    elapsed = time.time() - started

    print("\n" + "=" * 55)
    print("              PRODUCTION COMPLETE")
    print("=" * 55)
    print(f"Output: {FINAL_VIDEO}")
    print(f"Processing time: {elapsed / 60:.1f} minutes")
    print("Animated captions: YES")
    print("Background music: YES")
    print("AI footage selection: YES")
    print("Automatic video rendering: YES")

    # Open final video automatically
    if hasattr(os, "startfile"):
        os.startfile(str(FINAL_VIDEO))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nPRODUCTION FAILED: {error}")
        sys.exit(1)
