
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
AUDIO = BASE / "input" / "narration.wav"
TIMESTAMPS = BASE / "output" / "timestamps.json"
OUTPUT = BASE / "output"

OUTPUT.mkdir(exist_ok=True)

def srt_time(seconds):
    milliseconds = round(max(0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"

if not AUDIO.exists():
    raise FileNotFoundError(f"Missing audio: {AUDIO}")

if not TIMESTAMPS.exists():
    raise FileNotFoundError(f"Missing timestamps: {TIMESTAMPS}")

words = json.loads(TIMESTAMPS.read_text(encoding="utf-8"))

if not words:
    raise RuntimeError("No transcribed words found.")

print("Generating synchronised subtitles...")

blocks = []
group = []

for word in words:
    if group and (
        len(group) >= 6
        or word["start"] - group[-1]["end"] > 0.7
    ):
        blocks.append(group)
        group = []

    group.append(word)

if group:
    blocks.append(group)

subtitles = []

for index, block in enumerate(blocks, start=1):
    start = srt_time(block[0]["start"])
    end = srt_time(block[-1]["end"])
    text = " ".join(w["word"] for w in block)

    subtitles.append(
        f"{index}\n{start} --> {end}\n{text}\n"
    )

srt_file = OUTPUT / "captions.srt"
srt_file.write_text(
    "\n".join(subtitles),
    encoding="utf-8"
)

print(f"Created {len(blocks)} subtitle segments.")

print("Rendering video using FFmpeg...")

filter_string = (
    "subtitles=output/captions.srt:"
    "force_style='FontName=Arial,"
    "FontSize=24,"
    "PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,"
    "BorderStyle=1,"
    "Outline=2,"
    "Alignment=2,"
    "MarginV=90'"
)

command = [
    "ffmpeg",
    "-y",
    "-f", "lavfi",
    "-i", "color=c=0x101820:s=1280x720:r=30",
    "-i", str(AUDIO),
    "-vf", filter_string,
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "22",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac",
    "-b:a", "192k",
    "-shortest",
    str(OUTPUT / "test_video.mp4")
]

subprocess.run(
    command,
    cwd=BASE,
    check=True
)

print("\nVIDEO GENERATED SUCCESSFULLY!")
print(OUTPUT / "test_video.mp4")
