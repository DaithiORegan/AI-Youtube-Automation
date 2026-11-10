
from faster_whisper import WhisperModel
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent
AUDIO = BASE / "input" / "narration.wav"
OUTPUT = BASE / "output"

OUTPUT.mkdir(exist_ok=True)

if not AUDIO.exists():
    raise FileNotFoundError(
        f"Recording not found: {AUDIO}"
    )

print("Loading Whisper speech recognition model...")

# Start with CPU mode for compatibility.
# We can optimise GPU acceleration later.
model = WhisperModel(
    "base.en",
    device="cpu",
    compute_type="int8"
)

print("Transcribing narration...")

segments, info = model.transcribe(
    str(AUDIO),
    language="en",
    word_timestamps=True,
    vad_filter=True
)

words = []
transcript = []

for segment in segments:
    transcript.append(segment.text.strip())

    for word in segment.words or []:
        words.append({
            "start": round(word.start, 3),
            "end": round(word.end, 3),
            "word": word.word.strip()
        })

(OUTPUT / "transcript.txt").write_text(
    " ".join(transcript),
    encoding="utf-8"
)

(OUTPUT / "timestamps.json").write_text(
    json.dumps(words, indent=2),
    encoding="utf-8"
)

print("Transcription complete!")
print(f"Detected {len(words)} words.")
print("Saved transcript.txt and timestamps.json")
