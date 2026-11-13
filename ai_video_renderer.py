
import json
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
FOOTAGE = BASE / "assets" / "footage"
OUTPUT = BASE / "output"

PLAN = OUTPUT / "scene_plan_ready.json"
AUDIO = BASE / "input" / "narration.wav"
MUSIC = BASE / "assets" / "music" / "background.mp3"
CAPTIONS = OUTPUT / "captions.ass"
FINAL = OUTPUT / "ai_documentary.mp4"

# =====================================
# VIDEO QUALITY
# =====================================

WIDTH = 1920
HEIGHT = 1080
FPS = 30

PRESET = "slow"
CRF = 17

MIN_WIDTH = 1920
MIN_HEIGHT = 1080

# =====================================
# AUDIO SETTINGS
# =====================================

MUSIC_VOLUME = 0.08
MUSIC_FADE_IN = 1.0
MUSIC_FADE_OUT = 2.0

AUDIO_BITRATE = "320k"
AUDIO_SAMPLE_RATE = 48000


def run(command):
    subprocess.run(
        command,
        cwd=BASE,
        check=True
    )


def probe(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    return json.loads(result.stdout)


def duration(path):
    return float(
        probe(path)["format"]["duration"]
    )


def resolution(path):
    data = probe(path)

    for stream in data["streams"]:
        if stream.get("codec_type") == "video":
            return (
                int(stream.get("width", 0)),
                int(stream.get("height", 0))
            )

    return 0, 0


def validate_footage(filename):
    if not filename:
        return None

    path = (FOOTAGE / filename).resolve()

    if path.parent != FOOTAGE.resolve():
        print(f"Rejected unsafe path: {filename}")
        return None

    if not path.is_file():
        print(f"Missing footage: {filename}")
        return None

    width, height = resolution(path)

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        print(
            f"REJECTED: {filename} "
            f"({width}x{height}) below 1080p"
        )
        return None

    print(
        f"Accepted: {filename} "
        f"({width}x{height})"
    )

    return path


def main():
    started = time.time()

    OUTPUT.mkdir(parents=True, exist_ok=True)

    for path in (PLAN, AUDIO, MUSIC, CAPTIONS):
        if not path.is_file():
            raise FileNotFoundError(path)

    scenes = json.loads(
        PLAN.read_text(encoding="utf-8")
    )

    if not scenes:
        raise RuntimeError("Scene plan is empty.")

    scenes.sort(
        key=lambda scene: float(scene["start"])
    )

    audio_length = duration(AUDIO)

    boundaries = [0.0]

    for scene in scenes[1:]:
        start = float(scene["start"])

        if not boundaries[-1] < start < audio_length:
            raise ValueError(
                "Invalid scene boundaries."
            )

        boundaries.append(start)

    boundaries.append(audio_length)

    print("=" * 55)
    print("YOUTUBE AI - HIGH QUALITY RENDERER")
    print("=" * 55)
    print(f"Scenes: {len(scenes)}")
    print(f"Duration: {audio_length:.2f} seconds")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"FPS: {FPS}")
    print(f"Preset: {PRESET}")
    print(f"CRF: {CRF}")

    inputs = []
    filters = []

    # =====================================
    # BUILD VIDEO INPUTS
    # =====================================

    for index, scene in enumerate(scenes):
        seconds = boundaries[index + 1] - boundaries[index]

        if seconds <= 0:
            raise ValueError(
                f"Invalid scene duration: {index + 1}"
            )

        source = validate_footage(
            scene.get("filename")
        )

        if source is None:
            raise ValueError(f"Scene {index + 1} has no valid footage; source it before rendering. Dark fallbacks are disabled.")

        else:
            print(
                f"Scene {index + 1}: "
                f"{source.name}"
            )

            inputs.extend([
                "-stream_loop", "-1",
                "-i", str(source)
            ])

            video_filter = (
                f"[{index}:v]"
                f"fps={FPS},"
                f"scale={WIDTH}:{HEIGHT}:"
                "flags=lanczos:"
                "force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},"
                "setsar=1,"
                f"trim=duration={seconds:.6f},"
                "setpts=PTS-STARTPTS,"
                "format=yuv420p"
                f"[v{index}]"
            )

        filters.append(video_filter)

    # =====================================
    # CONCATENATE VIDEO SCENES
    # =====================================

    concat_inputs = "".join(
        f"[v{i}]" for i in range(len(scenes))
    )

    filters.append(
        f"{concat_inputs}"
        f"concat=n={len(scenes)}:v=1:a=0,"
        "ass=filename='output/captions.ass',"
        "format=yuv420p"
        "[videoout]"
    )

    # =====================================
    # MIX NARRATION AND MUSIC
    # =====================================

    narration_index = len(scenes)
    music_index = narration_index + 1

    fade_in = min(
        MUSIC_FADE_IN,
        audio_length / 3
    )

    fade_out = min(
        MUSIC_FADE_OUT,
        audio_length / 3
    )

    fade_start = max(
        0,
        audio_length - fade_out
    )

    filters.append(
        f"[{narration_index}:a]"
        f"aresample={AUDIO_SAMPLE_RATE},"
        "volume=1.0,"
        "asetpts=PTS-STARTPTS"
        "[narration]"
    )

    filters.append(
        f"[{music_index}:a]"
        f"aresample={AUDIO_SAMPLE_RATE},"
        f"volume={MUSIC_VOLUME},"
        "asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade_in:.3f},"
        f"afade=t=out:st={fade_start:.3f}:d={fade_out:.3f}"
        "[music]"
    )

    filters.append(
        "[narration][music]"
        "amix=inputs=2:"
        "duration=first:"
        "dropout_transition=0:"
        "normalize=0,"
        "alimiter=limit=0.95"
        "[audioout]"
    )

    filter_complex = ";".join(filters)

    # =====================================
    # FINAL SINGLE-PASS RENDER
    # =====================================

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "warning",

        *inputs,

        "-i", str(AUDIO),

        "-stream_loop", "-1",
        "-i", str(MUSIC),

        "-filter_complex",
        filter_complex,

        "-map", "[videoout]",
        "-map", "[audioout]",

        "-c:v", "libx264",
        "-preset", PRESET,
        "-crf", str(CRF),
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),

        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-ar", str(AUDIO_SAMPLE_RATE),

        "-t", f"{audio_length:.3f}",
        "-movflags", "+faststart",

        str(FINAL)
    ]

    print("\nStarting high-quality render...")

    run(command)

    if not FINAL.is_file():
        raise RuntimeError(
            "FFmpeg did not create the output."
        )

    width, height = resolution(FINAL)
    elapsed = time.time() - started

    print("\n" + "=" * 55)
    print("HIGH QUALITY VIDEO RENDERED SUCCESSFULLY")
    print("=" * 55)
    print(f"Output: {FINAL}")
    print(f"Resolution: {width}x{height}")
    print(f"Time: {elapsed / 60:.2f} minutes")
    print(
        f"File size: "
        f"{FINAL.stat().st_size / (1024**2):.1f} MB"
    )
    print("Narration: Included")
    print("Music: Included")
    print("Animated captions: Included")


if __name__ == "__main__":
    main()
