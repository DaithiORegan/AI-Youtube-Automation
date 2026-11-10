
import math
import json
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
FOOTAGE = BASE / "assets" / "footage"
OUTPUT = BASE / "output"
AUDIO = BASE / "input" / "narration.wav"
SUBTITLES = OUTPUT / "captions.srt"
FINAL = OUTPUT / "documentary_test.mp4"

SCENE_LENGTH = 5
FPS = 30
WIDTH = 1920
HEIGHT = 1080

def run(command):
    subprocess.run(
        command,
        cwd=BASE,
        check=True
    )

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
    return float(json.loads(result.stdout)["format"]["duration"])

def main():
    OUTPUT.mkdir(exist_ok=True)

    clips = sorted(FOOTAGE.glob("*.mp4"))

    if not clips:
        raise RuntimeError("No MP4 footage found.")

    if not AUDIO.exists():
        raise FileNotFoundError(f"Missing narration: {AUDIO}")

    if not SUBTITLES.exists():
        raise FileNotFoundError(f"Missing subtitles: {SUBTITLES}")

    duration = get_duration(AUDIO)
    # One extra second ensures footage covers the audio.
    scene_count = math.ceil((duration + 1) / SCENE_LENGTH)

    print(f"Found {len(clips)} footage clips.")
    print(f"Narration duration: {duration:.2f} seconds")
    print(f"Creating {scene_count} scenes...")

    with tempfile.TemporaryDirectory(
        dir=OUTPUT, prefix="render_"
    ) as temp:
        temp_dir = Path(temp)
        rendered = []

        for i in range(scene_count):
            source = clips[i % len(clips)]
            destination = temp_dir / f"scene_{i:04d}.mp4"

            print(
                f"Rendering scene {i + 1}/{scene_count}: "
                f"{source.name}",
                flush=True
            )

            run([
                "ffmpeg", "-y",
                "-hide_banner", "-loglevel", "error",
                "-stream_loop", "-1",
                "-i", str(source),
                "-vf",
                f"scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},"
                "setsar=1",
                "-an",
                "-r", str(FPS),
                "-frames:v", str(SCENE_LENGTH * FPS),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(destination)
            ])

            rendered.append(destination)

        concat_file = temp_dir / "clips.txt"
        concat_file.write_text(
            "\n".join(
                f"file '{p.as_posix()}'"
                for p in rendered
            ),
            encoding="utf-8"
        )

        combined = temp_dir / "combined.mp4"

        print("Combining footage...")

        run([
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(combined)
        ])

        print("Adding narration and subtitles...")

        subtitle_filter = (
            "subtitles=output/captions.srt:"
            "force_style='FontName=Arial,"
            "FontSize=20,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,"
            "Alignment=2,"
            "MarginV=80'"
        )

        run([
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error",
            "-i", str(combined),
            "-i", str(AUDIO),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration),
            "-movflags", "+faststart",
            str(FINAL)
        ])

    print("\nVIDEO GENERATED SUCCESSFULLY!")
    print(f"Saved to: {FINAL}")

if __name__ == "__main__":
    main()
