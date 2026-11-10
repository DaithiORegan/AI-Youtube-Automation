
import json
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
FOOTAGE = BASE / "assets" / "footage"
OUTPUT = BASE / "output"

PLAN = OUTPUT / "scene_plan_ready.json"
AUDIO = BASE / "input" / "narration.wav"
MUSIC = BASE / "assets" / "music" / "background.mp3"
CAPTIONS = OUTPUT / "captions.ass"
FINAL = OUTPUT / "ai_documentary.mp4"

# Video settings
WIDTH = 1920
HEIGHT = 1080
FPS = 30

# Music settings
MUSIC_VOLUME = 0.08
MUSIC_FADE_IN = 1.0
MUSIC_FADE_OUT = 2.0


def run(command):
    subprocess.run(
        command,
        cwd=BASE,
        check=True
    )


def duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return float(result.stdout.strip())


def render_scene(source, seconds, destination):
    if source is None:
        inputs = [
            "-f", "lavfi",
            "-i",
            f"color=c=0x101820:s={WIDTH}x{HEIGHT}:r={FPS}"
        ]
        video_filter = "format=yuv420p"
    else:
        inputs = [
            "-stream_loop", "-1",
            "-i", str(source)
        ]
        video_filter = (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            "setsar=1,"
            f"fps={FPS},"
            "format=yuv420p"
        )

    frame_count = max(1, round(seconds * FPS))

    run([
        "ffmpeg", "-y",
        "-hide_banner",
        "-loglevel", "error",
        *inputs,
        "-map", "0:v:0",
        "-vf", video_filter,
        "-frames:v", str(frame_count),
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-r", str(FPS),
        "-pix_fmt", "yuv420p",
        str(destination)
    ])


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for path in (PLAN, AUDIO, MUSIC, CAPTIONS):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing required file: {path}"
            )

    scenes = json.loads(
        PLAN.read_text(encoding="utf-8")
    )

    if not scenes:
        raise RuntimeError("Scene plan is empty.")

    scenes.sort(key=lambda x: float(x["start"]))
    audio_length = duration(AUDIO)

    print(f"Planned scenes: {len(scenes)}")
    print(f"Narration duration: {audio_length:.2f}s")
    print(f"Music: {MUSIC.name}")
    print("Caption style: ASS word highlighting")

    boundaries = [0.0]

    for scene in scenes[1:]:
        start = float(scene["start"])

        if not boundaries[-1] < start < audio_length:
            raise ValueError(
                "Invalid or overlapping scene start times."
            )

        boundaries.append(start)

    boundaries.append(audio_length)

    with tempfile.TemporaryDirectory(
        dir=OUTPUT,
        prefix="ai_render_"
    ) as folder:

        temp = Path(folder)
        rendered = []

        # Render each scene according to the AI plan
        for index, scene in enumerate(scenes):
            length = boundaries[index + 1] - boundaries[index]

            if length <= 0:
                raise ValueError("Invalid scene duration.")

            filename = scene.get("filename")
            source = FOOTAGE / filename if filename else None

            if source is not None and not source.is_file():
                print(f"Footage missing: {filename}")
                source = None

            if source is None:
                print(f"Scene {index + 1}: Dark fallback")
            else:
                print(f"Scene {index + 1}: {source.name}")

            destination = temp / f"scene_{index:04d}.mp4"

            render_scene(source, length, destination)
            rendered.append(destination)

        # Combine the individual scenes
        concat_file = temp / "concat.txt"
        concat_file.write_text(
            "\n".join(
                f"file '{path.as_posix()}'"
                for path in rendered
            ),
            encoding="utf-8"
        )

        combined = temp / "combined.mp4"

        print("Combining scenes...")

        run([
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(combined)
        ])

        # Background music settings
        fade_in = min(MUSIC_FADE_IN, audio_length / 3)
        fade_out = min(MUSIC_FADE_OUT, audio_length / 3)
        fade_start = max(0, audio_length - fade_out)

        audio_filter = (
            "[1:a]volume=1.0[narration];"
            "[2:a]"
            f"volume={MUSIC_VOLUME},"
            f"afade=t=in:st=0:d={fade_in:.3f},"
            f"afade=t=out:st={fade_start:.3f}:d={fade_out:.3f}"
            "[music];"
            "[narration][music]"
            "amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0[mixed];"
            "[mixed]alimiter=limit=0.95[aout]"
        )

        print("Rendering narration, music and captions...")

        run([
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error",

            "-i", str(combined),
            "-i", str(AUDIO),

            "-stream_loop", "-1",
            "-i", str(MUSIC),

            "-filter_complex", audio_filter,

            "-map", "0:v:0",
            "-map", "[aout]",

            "-vf", "ass=output/captions.ass",

            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",

            "-c:a", "aac",
            "-b:a", "192k",

            "-t", f"{audio_length:.3f}",
            "-movflags", "+faststart",

            str(FINAL)
        ])

    print("\nAI DOCUMENTARY RENDERED!")
    print(f"Video: {FINAL}")
    print("Narration: Included")
    print("Music: Included")
    print("Highlighted captions: Included")


if __name__ == "__main__":
    main()
